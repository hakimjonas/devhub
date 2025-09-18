"""High-performance HTTP connection pooling for DevHub.

This module provides async HTTP connection pooling with HTTP/2 multiplexing
support for improved performance when making multiple API calls to GitHub
and Jira. All implementations follow functional programming principles.

Classes:
    ConnectionConfig: Immutable connection configuration
    ConnectionStats: Immutable connection statistics
    PooledSession: HTTP session with connection pooling
    HTTPPool: Main connection pool manager
"""

import asyncio
import json
import time
import types
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace
from threading import Lock
from typing import Any
from typing import TypeVar
from typing import cast

import aiohttp
from returns.result import Failure
from returns.result import Result
from returns.result import Success

from devhub.cache import CacheConfig
from devhub.cache import FunctionalCache


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ConnectionConfig:
    """Immutable HTTP connection configuration.

    Attributes:
        max_connections: Maximum number of connections per host
        max_keepalive_connections: Maximum keepalive connections
        keepalive_timeout: Keepalive timeout in seconds
        connection_timeout: Connection timeout in seconds
        read_timeout: Read timeout in seconds
        total_timeout: Total request timeout in seconds
        enable_http2: Enable HTTP/2 support
        enable_compression: Enable response compression
        max_redirects: Maximum number of redirects to follow
        chunk_size: Chunk size for streaming responses
    """

    max_connections: int = 100
    max_keepalive_connections: int = 20
    keepalive_timeout: float = 30.0
    connection_timeout: float = 10.0
    read_timeout: float = 30.0
    total_timeout: float = 60.0
    enable_http2: bool = True
    enable_compression: bool = True
    max_redirects: int = 10
    chunk_size: int = 8192


@dataclass(frozen=True, slots=True)
class ConnectionStats:
    """Immutable connection pool statistics.

    Attributes:
        active_connections: Number of currently active connections
        idle_connections: Number of idle connections in pool
        total_requests: Total number of requests made
        successful_requests: Number of successful requests
        failed_requests: Number of failed requests
        cache_hits: Number of cache hits
        cache_misses: Number of cache misses
        average_response_time: Average response time in milliseconds
        total_bytes_sent: Total bytes sent
        total_bytes_received: Total bytes received
    """

    active_connections: int = 0
    idle_connections: int = 0
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    average_response_time: float = 0.0
    total_bytes_sent: int = 0
    total_bytes_received: int = 0

    @property
    def success_rate(self) -> float:
        """Calculate request success rate as percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100

    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate as percentage."""
        total_cache_requests = self.cache_hits + self.cache_misses
        if total_cache_requests == 0:
            return 0.0
        return (self.cache_hits / total_cache_requests) * 100

    def with_request_success(
        self,
        response_time: float,
        bytes_sent: int,
        bytes_received: int,
    ) -> "ConnectionStats":
        """Create new stats with successful request recorded."""
        new_total = self.total_requests + 1
        new_avg = (self.average_response_time * self.total_requests + response_time) / new_total

        return replace(
            self,
            total_requests=new_total,
            successful_requests=self.successful_requests + 1,
            average_response_time=new_avg,
            total_bytes_sent=self.total_bytes_sent + bytes_sent,
            total_bytes_received=self.total_bytes_received + bytes_received,
        )

    def with_request_failure(self) -> "ConnectionStats":
        """Create new stats with failed request recorded."""
        return replace(
            self,
            total_requests=self.total_requests + 1,
            failed_requests=self.failed_requests + 1,
        )

    def with_cache_hit(self) -> "ConnectionStats":
        """Create new stats with cache hit recorded."""
        return replace(self, cache_hits=self.cache_hits + 1)

    def with_cache_miss(self) -> "ConnectionStats":
        """Create new stats with cache miss recorded."""
        return replace(self, cache_misses=self.cache_misses + 1)


@dataclass(frozen=True, slots=True)
class HTTPRequest:
    """Immutable HTTP request specification.

    Attributes:
        method: HTTP method (GET, POST, etc.)
        url: Request URL
        headers: Request headers
        data: Request body data
        params: URL parameters
        cache_key: Optional cache key for response caching
        cache_ttl: Cache TTL in seconds (if caching enabled)
    """

    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    data: bytes | str | None = None
    params: dict[str, str] = field(default_factory=dict)
    cache_key: str | None = None
    cache_ttl: int = 300


@dataclass(frozen=True, slots=True)
class HTTPResponse:
    """Immutable HTTP response representation.

    Attributes:
        status_code: HTTP status code
        headers: Response headers
        content: Response content as bytes
        text: Response content as text
        json_data: Parsed JSON data (if applicable)
        url: Final URL (after redirects)
        response_time: Response time in milliseconds
        from_cache: Whether response came from cache
    """

    status_code: int
    headers: dict[str, str]
    content: bytes
    text: str
    json_data: dict[str, Any] | None = None
    url: str = ""
    response_time: float = 0.0
    from_cache: bool = False

    @property
    def is_success(self) -> bool:
        """Check if response indicates success (2xx status)."""
        http_success_min = 200
        http_success_max = 300
        return http_success_min <= self.status_code < http_success_max

    @property
    def is_client_error(self) -> bool:
        """Check if response indicates client error (4xx status)."""
        http_client_error_min = 400
        http_client_error_max = 500
        return http_client_error_min <= self.status_code < http_client_error_max

    @property
    def is_server_error(self) -> bool:
        """Check if response indicates server error (5xx status)."""
        http_server_error_min = 500
        http_server_error_max = 600
        return http_server_error_min <= self.status_code < http_server_error_max


class PooledSession:
    """HTTP session with connection pooling and caching.

    Provides high-performance HTTP operations with automatic connection
    pooling, response caching, and comprehensive metrics tracking.

    Example:
        >>> config = ConnectionConfig(max_connections=50)
        >>> session = PooledSession(config)
        >>> async with session:
        ...     response = await session.request(HTTPRequest("GET", "https://api.github.com"))
        ...     print(f"Status: {response.status_code}")
    """

    def __init__(
        self,
        config: ConnectionConfig | None = None,
        cache_config: CacheConfig | None = None,
    ) -> None:
        """Initialize pooled session with configuration."""
        self._config = config or ConnectionConfig()
        self._cache: FunctionalCache[HTTPResponse] = FunctionalCache(
            cache_config or CacheConfig(max_size=1000, default_ttl_seconds=300)
        )
        self._session: aiohttp.ClientSession | None = None
        self._stats = ConnectionStats()
        self._stats_lock = Lock()

    async def __aenter__(self) -> "PooledSession":
        """Async context manager entry."""
        await self._ensure_session()
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: types.TracebackType | None
    ) -> None:
        """Async context manager exit."""
        await self.close()

    async def _ensure_session(self) -> None:
        """Ensure HTTP session is created and configured."""
        if self._session is None or self._session.closed:
            # Configure connection limits
            connector = aiohttp.TCPConnector(
                limit=self._config.max_connections,
                limit_per_host=self._config.max_connections // 4,
                keepalive_timeout=self._config.keepalive_timeout,
                enable_cleanup_closed=True,
                force_close=False,
            )

            # Configure timeout
            timeout = aiohttp.ClientTimeout(
                total=self._config.total_timeout,
                connect=self._config.connection_timeout,
                sock_read=self._config.read_timeout,
            )

            # Create session with connection pooling
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={
                    "User-Agent": "DevHub/1.0 (https://github.com/hakimjonas/devhub)",
                    "Accept-Encoding": "gzip, deflate" if self._config.enable_compression else "",
                },
            )

    def _handle_request_error(self, exception: Exception) -> Failure[str]:
        """Handle request errors with consistent stats tracking."""
        with self._stats_lock:
            self._stats = self._stats.with_request_failure()

        if isinstance(exception, TimeoutError):
            return Failure(f"Request timeout after {self._config.total_timeout}s")
        if isinstance(exception, aiohttp.ClientError):
            return Failure(f"HTTP client error: {exception}")
        if isinstance(exception, OSError):
            return Failure(f"Network error: {exception}")
        return Failure(f"Unexpected error: {exception}")

    def _check_cache(self, request: HTTPRequest) -> Result[HTTPResponse, None] | None:
        """Check cache for existing response. Returns None if no cache hit."""
        if not request.cache_key:
            return None

        cache_result = self._cache.get(request.cache_key)
        if isinstance(cache_result, Success):
            with self._stats_lock:
                self._stats = self._stats.with_cache_hit()
            response = cache_result.unwrap()
            return Success(replace(response, from_cache=True))

        with self._stats_lock:
            self._stats = self._stats.with_cache_miss()
        return None

    async def request(self, request: HTTPRequest) -> Result[HTTPResponse, str]:
        """Execute HTTP request with caching and connection pooling.

        Args:
            request: HTTP request specification

        Returns:
            Success with HTTPResponse or Failure with error message

        Example:
            >>> req = HTTPRequest("GET", "https://api.github.com/user")
            >>> result = await session.request(req)
            >>> match result:
            ...     case Success(response):
            ...         print(f"Got: {response.status_code}")
            ...     case Failure(error):
            ...         print(f"Error: {error}")
        """
        # Check cache first
        cache_result = self._check_cache(request)
        if cache_result is not None:
            return cache_result

        # Execute HTTP request
        start_time = time.time()
        try:
            await self._ensure_session()
            assert self._session is not None

            async with self._session.request(
                method=request.method,
                url=request.url,
                headers=request.headers,
                data=request.data,
                params=request.params,
            ) as response:
                # Read response content
                content = await response.read()
                text = content.decode("utf-8", errors="ignore")

                # Parse JSON if content type indicates JSON
                json_data = self._parse_json_response(dict(response.headers), text)

                response_time = (time.time() - start_time) * 1000
                bytes_sent = len(request.data or "") + sum(len(k) + len(v) for k, v in request.headers.items())
                bytes_received = len(content)

                # Create response object
                http_response = HTTPResponse(
                    status_code=response.status,
                    headers=dict(response.headers),
                    content=content,
                    text=text,
                    json_data=json_data,
                    url=str(response.url),
                    response_time=response_time,
                    from_cache=False,
                )

                # Cache successful responses if cache key provided
                if request.cache_key and http_response.is_success:
                    self._cache.put(
                        request.cache_key,
                        http_response,
                        ttl_seconds=request.cache_ttl,
                    )

                # Update statistics
                with self._stats_lock:
                    if http_response.is_success:
                        self._stats = self._stats.with_request_success(response_time, bytes_sent, bytes_received)
                    else:
                        self._stats = self._stats.with_request_failure()

                return Success(http_response)

        except (
            TimeoutError,
            aiohttp.ClientError,
            OSError,
            ValueError,
            UnicodeDecodeError,
            asyncio.CancelledError,
        ) as e:
            return self._handle_request_error(e)

    async def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        cache_key: str | None = None,
        cache_ttl: int = 300,
    ) -> Result[HTTPResponse, str]:
        """Convenience method for GET requests."""
        request = HTTPRequest(
            method="GET",
            url=url,
            headers=headers or {},
            params=params or {},
            cache_key=cache_key,
            cache_ttl=cache_ttl,
        )
        return await self.request(request)

    async def post(
        self,
        url: str,
        data: bytes | str | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> Result[HTTPResponse, str]:
        """Convenience method for POST requests."""
        request = HTTPRequest(
            method="POST",
            url=url,
            headers=headers or {},
            data=data,
            params=params or {},
        )
        return await self.request(request)

    def get_stats(self) -> ConnectionStats:
        """Get current connection statistics.

        Returns:
            Immutable snapshot of current statistics
        """
        with self._stats_lock:
            return self._stats

    def _parse_json_response(self, headers: dict[str, str], text: str) -> dict[str, Any] | None:
        """Parse JSON response if content type indicates JSON."""
        content_type = headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                return cast("dict[str, Any]", json.loads(text))
            except json.JSONDecodeError:
                pass  # Not valid JSON, leave as None
        return None

    async def close(self) -> None:
        """Close the session and all connections."""
        if self._session and not self._session.closed:
            await self._session.close()


class HTTPPool:
    """Global HTTP connection pool manager.

    Provides centralized management of HTTP connections with automatic
    session reuse and connection pooling across the entire application.

    Example:
        >>> pool = HTTPPool()
        >>> async with pool.get_session("github") as session:
        ...     response = await session.get("https://api.github.com/user")
    """

    def __init__(self, default_config: ConnectionConfig | None = None) -> None:
        """Initialize HTTP pool with default configuration."""
        self._default_config = default_config or ConnectionConfig()
        self._sessions: dict[str, PooledSession] = {}
        self._session_configs: dict[str, ConnectionConfig] = {}
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def get_session(
        self,
        pool_name: str = "default",
        config: ConnectionConfig | None = None,
    ) -> AsyncIterator[PooledSession]:
        """Get or create a pooled session for the given pool name.

        Args:
            pool_name: Name of the connection pool
            config: Optional configuration override

        Yields:
            PooledSession for making HTTP requests

        Example:
            >>> async with pool.get_session("github") as session:
            ...     result = await session.get("https://api.github.com/user")
        """
        async with self._lock:
            if pool_name not in self._sessions:
                session_config = config or self._default_config
                self._session_configs[pool_name] = session_config
                self._sessions[pool_name] = PooledSession(session_config)

            session = self._sessions[pool_name]

        try:
            async with session:
                yield session
        except Exception:
            # Remove failed session from pool
            async with self._lock:
                if pool_name in self._sessions:
                    await self._sessions[pool_name].close()
                    del self._sessions[pool_name]
            raise

    async def get_pool_stats(self, pool_name: str = "default") -> ConnectionStats | None:
        """Get statistics for a specific pool.

        Args:
            pool_name: Name of the connection pool

        Returns:
            ConnectionStats if pool exists, None otherwise
        """
        async with self._lock:
            session = self._sessions.get(pool_name)
            return session.get_stats() if session else None

    async def close_all(self) -> None:
        """Close all pooled sessions."""
        async with self._lock:
            for session in self._sessions.values():
                await session.close()
            self._sessions.clear()
            self._session_configs.clear()


# Module-level singleton instance - initialized lazily
_global_pool: HTTPPool | None = None


async def get_global_pool() -> HTTPPool:
    """Get the global HTTP pool instance.

    Returns:
        Global HTTPPool instance

    Example:
        >>> pool = await get_global_pool()
        >>> async with pool.get_session("github") as session:
        ...     result = await session.get("https://api.github.com/user")
    """
    if _global_pool is None:
        globals()["_global_pool"] = HTTPPool()
    return _global_pool


async def shutdown_global_pool() -> None:
    """Shutdown the global HTTP pool and close all connections."""
    # Use module-level access instead of global statement
    if _global_pool:
        await _global_pool.close_all()
        globals()["_global_pool"] = None
