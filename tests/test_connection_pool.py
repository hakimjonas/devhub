"""Tests for HTTP connection pooling module.

This module tests the HTTP connection pooling implementation including
session management, caching, and statistics tracking.
"""

import json
from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest
from aiohttp import ClientError
from hypothesis import given
from hypothesis import strategies as st
from returns.result import Failure
from returns.result import Success

from devhub.connection_pool import ConnectionConfig
from devhub.connection_pool import ConnectionStats
from devhub.connection_pool import HTTPPool
from devhub.connection_pool import HTTPRequest
from devhub.connection_pool import HTTPResponse
from devhub.connection_pool import PooledSession
from devhub.connection_pool import get_global_pool
from devhub.connection_pool import shutdown_global_pool


class TestConnectionConfig:
    """Test ConnectionConfig dataclass."""

    def test_connection_config_defaults(self) -> None:
        """Test default connection configuration."""
        config = ConnectionConfig()
        assert config.max_connections == 100
        assert config.keepalive_timeout == 30.0
        assert config.connection_timeout == 10.0
        assert config.enable_http2 is True
        assert config.enable_compression is True

    def test_connection_config_custom(self) -> None:
        """Test custom connection configuration."""
        config = ConnectionConfig(
            max_connections=50,
            keepalive_timeout=15.0,
            enable_http2=False,
        )
        assert config.max_connections == 50
        assert config.keepalive_timeout == 15.0
        assert config.enable_http2 is False

    def test_connection_config_immutability(self) -> None:
        """Test that connection config is immutable."""
        config = ConnectionConfig()
        with pytest.raises(AttributeError):
            config.max_connections = 200  # type: ignore[misc]


class TestConnectionStats:
    """Test ConnectionStats dataclass."""

    def test_connection_stats_defaults(self) -> None:
        """Test default connection statistics."""
        stats = ConnectionStats()
        assert stats.total_requests == 0
        assert stats.successful_requests == 0
        assert stats.failed_requests == 0
        assert stats.success_rate == 0.0
        assert stats.cache_hit_rate == 0.0

    def test_connection_stats_success_rate(self) -> None:
        """Test success rate calculation."""
        stats = ConnectionStats(total_requests=100, successful_requests=85)
        assert stats.success_rate == 85.0

        empty_stats = ConnectionStats()
        assert empty_stats.success_rate == 0.0

    def test_connection_stats_cache_hit_rate(self) -> None:
        """Test cache hit rate calculation."""
        stats = ConnectionStats(cache_hits=75, cache_misses=25)
        assert stats.cache_hit_rate == 75.0

        no_cache_stats = ConnectionStats()
        assert no_cache_stats.cache_hit_rate == 0.0

    def test_with_request_success(self) -> None:
        """Test recording successful request."""
        initial = ConnectionStats()

        updated = initial.with_request_success(
            response_time=150.0,
            bytes_sent=1024,
            bytes_received=2048,
        )

        assert updated.total_requests == 1
        assert updated.successful_requests == 1
        assert updated.average_response_time == 150.0
        assert updated.total_bytes_sent == 1024
        assert updated.total_bytes_received == 2048
        # Original unchanged
        assert initial.total_requests == 0

    def test_with_request_failure(self) -> None:
        """Test recording failed request."""
        initial = ConnectionStats()

        updated = initial.with_request_failure()

        assert updated.total_requests == 1
        assert updated.failed_requests == 1
        assert updated.successful_requests == 0

    def test_with_cache_operations(self) -> None:
        """Test cache hit/miss recording."""
        initial = ConnectionStats()

        with_hit = initial.with_cache_hit()
        assert with_hit.cache_hits == 1

        with_miss = with_hit.with_cache_miss()
        assert with_miss.cache_hits == 1
        assert with_miss.cache_misses == 1

    def test_average_response_time_calculation(self) -> None:
        """Test average response time calculation with multiple requests."""
        stats = ConnectionStats()

        # First request: 100ms
        stats = stats.with_request_success(100.0, 512, 1024)
        assert stats.average_response_time == 100.0

        # Second request: 200ms, average should be 150ms
        stats = stats.with_request_success(200.0, 512, 1024)
        assert stats.average_response_time == 150.0

    def test_connection_stats_immutability(self) -> None:
        """Test that connection stats are immutable."""
        stats = ConnectionStats()
        with pytest.raises(AttributeError):
            stats.total_requests = 10  # type: ignore[misc]


class TestHTTPRequest:
    """Test HTTPRequest dataclass."""

    def test_http_request_creation(self) -> None:
        """Test creating HTTP request."""
        request = HTTPRequest(
            method="GET",
            url="https://api.github.com/user",
            headers={"Authorization": "token secret"},
            cache_key="github_user",
        )

        assert request.method == "GET"
        assert request.url == "https://api.github.com/user"
        assert request.headers["Authorization"] == "token secret"
        assert request.cache_key == "github_user"
        assert request.cache_ttl == 300  # default

    def test_http_request_with_data(self) -> None:
        """Test HTTP request with POST data."""
        data = json.dumps({"key": "value"})
        request = HTTPRequest(
            method="POST",
            url="https://api.example.com",
            data=data,
            headers={"Content-Type": "application/json"},
        )

        assert request.method == "POST"
        assert request.data == data

    def test_http_request_immutability(self) -> None:
        """Test that HTTP request is immutable."""
        request = HTTPRequest("GET", "https://example.com")
        with pytest.raises(AttributeError):
            request.method = "POST"  # type: ignore[misc]


class TestHTTPResponse:
    """Test HTTPResponse dataclass."""

    def test_http_response_creation(self) -> None:
        """Test creating HTTP response."""
        response = HTTPResponse(
            status_code=200,
            headers={"Content-Type": "application/json"},
            content=b'{"success": true}',
            text='{"success": true}',
            json_data={"success": True},
            response_time=125.5,
        )

        assert response.status_code == 200
        assert response.json_data == {"success": True}
        assert response.response_time == 125.5
        assert response.is_success is True
        assert response.is_client_error is False
        assert response.is_server_error is False

    def test_http_response_status_checks(self) -> None:
        """Test HTTP response status checking methods."""
        # Success response
        success_response = HTTPResponse(
            status_code=201,
            headers={},
            content=b"",
            text="",
        )
        assert success_response.is_success is True

        # Client error response
        client_error = HTTPResponse(
            status_code=404,
            headers={},
            content=b"",
            text="",
        )
        assert client_error.is_client_error is True
        assert client_error.is_success is False

        # Server error response
        server_error = HTTPResponse(
            status_code=500,
            headers={},
            content=b"",
            text="",
        )
        assert server_error.is_server_error is True
        assert server_error.is_success is False

    def test_http_response_immutability(self) -> None:
        """Test that HTTP response is immutable."""
        response = HTTPResponse(200, {}, b"", "")
        with pytest.raises(AttributeError):
            response.status_code = 404  # type: ignore[misc]


class TestPooledSession:
    """Test PooledSession functionality."""

    @pytest.mark.asyncio
    async def test_pooled_session_context_manager(self) -> None:
        """Test PooledSession as async context manager."""
        config = ConnectionConfig(max_connections=10)
        session = PooledSession(config)

        async with session:
            # Session should be created
            assert session._session is not None

        # Session should be closed after exit
        assert session._session is None or session._session.closed

    @pytest.mark.asyncio
    async def test_pooled_session_ensure_session(self) -> None:
        """Test session creation and configuration."""
        config = ConnectionConfig(
            max_connections=50,
            connection_timeout=5.0,
            enable_compression=False,
        )
        session = PooledSession(config)

        await session._ensure_session()

        assert session._session is not None
        assert not session._session.closed

        await session.close()

    @pytest.mark.asyncio
    async def test_pooled_session_request_with_mock(self) -> None:
        """Test HTTP request execution with mocked aiohttp."""
        session = PooledSession()

        # Mock aiohttp response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.read.return_value = b'{"test": "data"}'
        mock_response.url = "https://api.example.com"

        # Create a proper async context manager mock
        class MockAsyncContextManager:
            def __init__(self, response) -> None:
                self.response = response

            async def __aenter__(self) -> AsyncMock:
                return self.response  # type: ignore[no-any-return]

            async def __aexit__(
                self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: object
            ) -> None:
                return None

        # Mock session with proper async context manager
        mock_session = AsyncMock()

        # Override the request method to return our custom context manager
        def mock_request(method: str, url: str, **kwargs: object) -> MockAsyncContextManager:
            return MockAsyncContextManager(mock_response)

        mock_session.request = mock_request
        mock_session.closed = False

        session._session = mock_session

        request = HTTPRequest("GET", "https://api.example.com")
        result = await session.request(request)

        assert isinstance(result, Success)
        response = result.unwrap()
        assert response.status_code == 200
        assert response.json_data == {"test": "data"}
        assert response.is_success

    @pytest.mark.asyncio
    async def test_pooled_session_request_timeout(self) -> None:
        """Test request timeout handling."""
        config = ConnectionConfig(total_timeout=0.001)  # Very short timeout
        session = PooledSession(config)

        # Create a context manager that raises TimeoutError
        class TimeoutAsyncContextManager:
            async def __aenter__(self) -> AsyncMock:
                msg = "Request timeout"
                raise TimeoutError(msg)

            async def __aexit__(
                self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: object
            ) -> None:
                return None

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()

            # Override the request method to return our timeout context manager
            def mock_request(method: str, url: str, **kwargs: object) -> TimeoutAsyncContextManager:
                return TimeoutAsyncContextManager()

            mock_session.request = mock_request
            mock_session_class.return_value = mock_session

            request = HTTPRequest("GET", "https://httpbin.org/delay/5")
            result = await session.request(request)

            assert isinstance(result, Failure)
            assert "timeout" in str(result).lower()

    @pytest.mark.asyncio
    async def test_pooled_session_request_client_error(self) -> None:
        """Test client error handling."""
        session = PooledSession()

        # Create a context manager that raises ClientError
        class ClientErrorAsyncContextManager:
            async def __aenter__(self) -> AsyncMock:
                msg = "Connection failed"
                raise ClientError(msg)

            async def __aexit__(
                self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: object
            ) -> None:
                return None

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()

            # Override the request method to return our error context manager
            def mock_request(method: str, url: str, **kwargs: object) -> ClientErrorAsyncContextManager:
                return ClientErrorAsyncContextManager()

            mock_session.request = mock_request
            mock_session_class.return_value = mock_session

            request = HTTPRequest("GET", "https://invalid.example.com")
            result = await session.request(request)

            assert isinstance(result, Failure)
            assert "client error" in str(result).lower()

    @pytest.mark.asyncio
    async def test_pooled_session_caching(self) -> None:
        """Test response caching functionality."""
        session = PooledSession()

        # Mock successful response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {"Content-Type": "text/plain"}
        mock_response.read.return_value = b"cached content"
        mock_response.url = "https://api.example.com"

        # Create a proper async context manager mock
        class MockAsyncContextManager:
            def __init__(self, response) -> None:
                self.response = response

            async def __aenter__(self) -> AsyncMock:
                return self.response  # type: ignore[no-any-return]

            async def __aexit__(
                self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: object
            ) -> None:
                return None

        # Create a mock function that tracks call count
        class MockRequest:
            def __init__(self) -> None:
                self.call_count = 0

            def __call__(self, *, method: str, url: str, **_kwargs: object) -> MockAsyncContextManager:  # noqa: ARG002
                self.call_count += 1
                return MockAsyncContextManager(mock_response)

        mock_session = AsyncMock()
        mock_session.request = MockRequest()
        mock_session.closed = False
        session._session = mock_session

        # First request - should hit the mock
        request = HTTPRequest(
            "GET",
            "https://api.example.com",
            cache_key="test_cache",
            cache_ttl=60,
        )
        result1 = await session.request(request)
        assert isinstance(result1, Success)
        assert not result1.unwrap().from_cache

        # Second request with same cache key - should hit cache
        result2 = await session.request(request)
        assert isinstance(result2, Success)
        assert result2.unwrap().from_cache

        # Verify mock was only called once
        assert mock_session.request.call_count == 1

    @pytest.mark.asyncio
    async def test_pooled_session_convenience_methods(self) -> None:
        """Test GET and POST convenience methods."""
        session = PooledSession()

        # Mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {}
        mock_response.read.return_value = b"response"
        mock_response.url = "https://api.example.com"

        # Create a proper async context manager mock
        class MockAsyncContextManager:
            def __init__(self, response) -> None:
                self.response = response

            async def __aenter__(self) -> AsyncMock:
                return self.response  # type: ignore[no-any-return]

            async def __aexit__(
                self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: object
            ) -> None:
                return None

        mock_session = AsyncMock()

        # Override the request method to return our custom context manager
        def mock_request(method: str, url: str, **kwargs: object) -> MockAsyncContextManager:
            return MockAsyncContextManager(mock_response)

        mock_session.request = mock_request
        mock_session.closed = False
        session._session = mock_session

        # Test GET
        get_result = await session.get(
            "https://api.example.com",
            headers={"Accept": "application/json"},
            cache_key="get_test",
        )
        assert isinstance(get_result, Success)

        # Test POST
        post_result = await session.post(
            "https://api.example.com",
            data='{"test": "data"}',
            headers={"Content-Type": "application/json"},
        )
        assert isinstance(post_result, Success)

    def test_pooled_session_get_stats(self) -> None:
        """Test getting session statistics."""
        session = PooledSession()
        stats = session.get_stats()

        assert isinstance(stats, ConnectionStats)
        assert stats.total_requests == 0

    @pytest.mark.asyncio
    async def test_pooled_session_stats_updates(self) -> None:
        """Test that statistics are updated correctly."""
        session = PooledSession()

        # Mock successful response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {}
        mock_response.read.return_value = b"success"
        mock_response.url = "https://api.example.com"

        # Create a proper async context manager mock
        class MockAsyncContextManager:
            def __init__(self, response) -> None:
                self.response = response

            async def __aenter__(self) -> AsyncMock:
                return self.response  # type: ignore[no-any-return]

            async def __aexit__(
                self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: object
            ) -> None:
                return None

        mock_session = AsyncMock()

        # Override the request method to return our custom context manager
        def mock_request(method: str, url: str, **kwargs: object) -> MockAsyncContextManager:
            return MockAsyncContextManager(mock_response)

        mock_session.request = mock_request
        mock_session.closed = False
        session._session = mock_session

        request = HTTPRequest("GET", "https://api.example.com")
        await session.request(request)

        stats = session.get_stats()
        assert stats.total_requests == 1
        assert stats.successful_requests == 1
        assert stats.average_response_time > 0


class TestHTTPPool:
    """Test HTTPPool functionality."""

    @pytest.mark.asyncio
    async def test_http_pool_get_session(self) -> None:
        """Test getting session from pool."""
        pool = HTTPPool()

        async with pool.get_session("test_pool") as session:
            assert isinstance(session, PooledSession)

        # Session should be reused
        async with pool.get_session("test_pool") as session2:
            assert isinstance(session2, PooledSession)

        await pool.close_all()

    @pytest.mark.asyncio
    async def test_http_pool_different_configs(self) -> None:
        """Test pool with different configurations."""
        pool = HTTPPool()

        config1 = ConnectionConfig(max_connections=50)
        config2 = ConnectionConfig(max_connections=100)

        async with pool.get_session("pool1", config1) as session1:
            assert session1._config.max_connections == 50

        async with pool.get_session("pool2", config2) as session2:
            assert session2._config.max_connections == 100

        await pool.close_all()

    @pytest.mark.asyncio
    async def test_http_pool_stats(self) -> None:
        """Test getting pool statistics."""
        pool = HTTPPool()

        # No stats for non-existent pool
        stats = await pool.get_pool_stats("nonexistent")
        assert stats is None

        # Create pool and get stats
        async with pool.get_session("test_pool"):
            pass

        stats = await pool.get_pool_stats("test_pool")
        assert isinstance(stats, ConnectionStats)

        await pool.close_all()

    @pytest.mark.asyncio
    async def test_http_pool_error_handling(self) -> None:
        """Test pool error handling and session cleanup."""
        pool = HTTPPool()

        # Simulate session creation that fails
        with patch("devhub.connection_pool.PooledSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session.__aenter__.side_effect = Exception("Session error")
            mock_session_class.return_value = mock_session

            with pytest.raises(Exception, match="Session error"):
                async with pool.get_session("failing_pool"):
                    pass

        # Pool should be cleaned up
        stats = await pool.get_pool_stats("failing_pool")
        assert stats is None

        await pool.close_all()

    @pytest.mark.asyncio
    async def test_http_pool_close_all(self) -> None:
        """Test closing all pooled sessions."""
        pool = HTTPPool()

        # Create multiple sessions
        async with pool.get_session("pool1"):
            pass
        async with pool.get_session("pool2"):
            pass

        # Verify sessions exist
        assert await pool.get_pool_stats("pool1") is not None
        assert await pool.get_pool_stats("pool2") is not None

        # Close all
        await pool.close_all()

        # Verify sessions are gone
        assert await pool.get_pool_stats("pool1") is None
        assert await pool.get_pool_stats("pool2") is None


class TestGlobalPool:
    """Test global pool functions."""

    @pytest.mark.asyncio
    async def test_get_global_pool(self) -> None:
        """Test getting global pool instance."""
        pool1 = await get_global_pool()
        pool2 = await get_global_pool()

        # Should return same instance
        assert pool1 is pool2

        await shutdown_global_pool()

    @pytest.mark.asyncio
    async def test_shutdown_global_pool(self) -> None:
        """Test shutting down global pool."""
        pool = await get_global_pool()

        # Create a session to verify cleanup
        async with pool.get_session("test"):
            pass

        await shutdown_global_pool()

        # Getting pool again should create new instance
        new_pool = await get_global_pool()
        assert new_pool is not pool

        await shutdown_global_pool()


class TestPropertyBased:
    """Property-based tests for connection pool."""

    @given(
        st.integers(min_value=1, max_value=1000),
        st.floats(min_value=0.1, max_value=60.0),
    )
    def test_connection_config_properties(
        self,
        max_connections: int,
        timeout: float,
    ) -> None:
        """Test connection config with various values."""
        config = ConnectionConfig(
            max_connections=max_connections,
            connection_timeout=timeout,
        )

        assert config.max_connections == max_connections
        assert config.connection_timeout == timeout
        assert config.max_connections > 0
        assert config.connection_timeout > 0

    @given(
        st.integers(min_value=0, max_value=1000),
        st.integers(min_value=0, max_value=1000),
    )
    def test_connection_stats_properties(
        self,
        successful: int,
        failed: int,
    ) -> None:
        """Test connection stats with various values."""
        total = successful + failed
        stats = ConnectionStats(
            total_requests=total,
            successful_requests=successful,
            failed_requests=failed,
        )

        assert stats.total_requests == total
        assert stats.successful_requests == successful
        assert stats.failed_requests == failed

        if total > 0:
            assert 0 <= stats.success_rate <= 100
        else:
            assert stats.success_rate == 0

    @given(st.text(min_size=1), st.text(min_size=1))
    def test_http_request_properties(self, method: str, url: str) -> None:
        """Test HTTP request with various inputs."""
        request = HTTPRequest(method=method, url=url)

        assert request.method == method
        assert request.url == url
        assert isinstance(request.headers, dict)
        assert isinstance(request.params, dict)
