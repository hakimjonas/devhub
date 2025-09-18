"""Immutable caching layer for DevHub with TTL support.

This module provides a functional, thread-safe caching implementation
using immutable data structures and pure functions. All cache operations
return new instances rather than modifying existing state.

Classes:
    CacheEntry: Immutable cache entry with value and metadata
    CacheStats: Immutable cache statistics
    CacheConfig: Immutable cache configuration
    FunctionalCache: Thread-safe cache with LRU eviction and TTL
"""

import hashlib
import json
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace
from threading import Lock
from typing import TypeVar

from returns.result import Failure
from returns.result import Result
from returns.result import Success


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class CacheEntry[T]:
    """Immutable cache entry with TTL and access tracking.

    Attributes:
        value: The cached value
        expires_at: Unix timestamp when entry expires
        created_at: Unix timestamp when entry was created
        access_count: Number of times entry has been accessed
        last_accessed: Unix timestamp of last access
    """

    value: T
    expires_at: float
    created_at: float
    access_count: int = 1
    last_accessed: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return time.time() > self.expires_at

    def with_access(self) -> "CacheEntry[T]":
        """Create new entry with incremented access count."""
        return replace(
            self,
            access_count=self.access_count + 1,
            last_accessed=time.time(),
        )


@dataclass(frozen=True, slots=True)
class CacheStats:
    """Immutable cache statistics.

    Attributes:
        hits: Number of cache hits
        misses: Number of cache misses
        evictions: Number of entries evicted
        expirations: Number of entries expired
        total_requests: Total number of cache requests
    """

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    expirations: int = 0
    total_requests: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate as percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.hits / self.total_requests) * 100

    def with_hit(self) -> "CacheStats":
        """Create new stats with incremented hit count."""
        return replace(
            self,
            hits=self.hits + 1,
            total_requests=self.total_requests + 1,
        )

    def with_miss(self) -> "CacheStats":
        """Create new stats with incremented miss count."""
        return replace(
            self,
            misses=self.misses + 1,
            total_requests=self.total_requests + 1,
        )

    def with_eviction(self) -> "CacheStats":
        """Create new stats with incremented eviction count."""
        return replace(self, evictions=self.evictions + 1)

    def with_expiration(self) -> "CacheStats":
        """Create new stats with incremented expiration count."""
        return replace(self, expirations=self.expirations + 1)


@dataclass(frozen=True, slots=True)
class CacheConfig:
    """Immutable cache configuration.

    Attributes:
        max_size: Maximum number of entries in cache
        default_ttl_seconds: Default time-to-live for entries
        check_expired_interval: Seconds between expired entry cleanup
        enable_stats: Whether to track cache statistics
    """

    max_size: int = 1000
    default_ttl_seconds: int = 300
    check_expired_interval: int = 60
    enable_stats: bool = True


class FunctionalCache[T]:
    """Thread-safe cache implementation with LRU eviction and TTL support.

    This cache maintains immutability principles by never modifying
    cache entries directly. All operations that would modify state
    return new instances or use thread-safe internal updates.

    Example:
        >>> cache = FunctionalCache[str](CacheConfig(max_size=100))
        >>> result = cache.get_or_compute("key", lambda: "value")
        >>> match result:
        ...     case Success(value):
        ...         print(f"Got: {value}")
        ...     case Failure(error):
        ...         print(f"Error: {error}")
    """

    def __init__(self, config: CacheConfig | None = None) -> None:
        """Initialize cache with configuration."""
        self._config = config or CacheConfig()
        self._cache: OrderedDict[str, CacheEntry[T]] = OrderedDict()
        self._stats = CacheStats()
        self._lock = Lock()
        self._last_cleanup = time.time()

    @staticmethod
    def _make_key(*args: object, **kwargs: object) -> str:
        """Create cache key from arguments using deterministic hashing."""
        key_data = {
            "args": args,
            "kwargs": sorted(kwargs.items()),
        }
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.sha256(key_str.encode()).hexdigest()

    def get(self, key: str) -> Result[T, str]:
        """Get value from cache if present and not expired.

        Args:
            key: Cache key to look up

        Returns:
            Success with cached value if found and valid,
            Failure with reason if not found or expired
        """
        with self._lock:
            self._maybe_cleanup_expired()

            if key not in self._cache:
                if self._config.enable_stats:
                    self._stats = self._stats.with_miss()
                return Failure(f"Cache miss for key: {key}")

            entry = self._cache[key]

            if entry.is_expired():
                del self._cache[key]
                if self._config.enable_stats:
                    self._stats = self._stats.with_expiration().with_miss()
                return Failure(f"Cache entry expired for key: {key}")

            # Update access count and move to end (most recently used)
            self._cache[key] = entry.with_access()
            self._cache.move_to_end(key)

            if self._config.enable_stats:
                self._stats = self._stats.with_hit()

            return Success(entry.value)

    def put(
        self,
        key: str,
        value: T,
        ttl_seconds: int | None = None,
    ) -> Result[None, str]:
        """Add or update value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Optional TTL override

        Returns:
            Success if cached successfully, Failure if error
        """
        ttl = ttl_seconds or self._config.default_ttl_seconds

        with self._lock:
            # Evict LRU entry if at max size
            if len(self._cache) >= self._config.max_size and key not in self._cache:
                lru_key = next(iter(self._cache))
                del self._cache[lru_key]
                if self._config.enable_stats:
                    self._stats = self._stats.with_eviction()

            now = time.time()
            entry = CacheEntry(
                value=value,
                expires_at=now + ttl,
                created_at=now,
            )

            self._cache[key] = entry
            self._cache.move_to_end(key)

            return Success(None)

    def get_or_compute(
        self,
        key: str,
        compute_fn: Callable[[], T],
        ttl_seconds: int | None = None,
    ) -> Result[T, str]:
        """Get from cache or compute and cache if missing.

        Args:
            key: Cache key
            compute_fn: Function to compute value if not cached
            ttl_seconds: Optional TTL override

        Returns:
            Success with value (cached or computed), Failure if error
        """
        # Try to get from cache first
        cache_result = self.get(key)
        if isinstance(cache_result, Success):
            return cache_result

        # Compute value if not in cache
        try:
            value = compute_fn()
            # Cache the computed value
            put_result = self.put(key, value, ttl_seconds)
            if isinstance(put_result, Failure):
                return put_result
            return Success(value)
        except (ValueError, TypeError, AttributeError, RuntimeError) as e:
            return Failure(f"Failed to compute value: {e}")

    def invalidate(self, key: str) -> Result[None, str]:
        """Remove entry from cache.

        Args:
            key: Cache key to invalidate

        Returns:
            Success if invalidated or not present, Failure if error
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
            return Success(None)

    def clear(self) -> Result[None, str]:
        """Clear all entries from cache.

        Returns:
            Success if cleared, Failure if error
        """
        with self._lock:
            self._cache.clear()
            self._stats = CacheStats()
            return Success(None)

    def get_stats(self) -> CacheStats:
        """Get current cache statistics.

        Returns:
            Immutable cache statistics snapshot
        """
        with self._lock:
            return self._stats

    def size(self) -> int:
        """Get current number of entries in cache.

        Returns:
            Number of cached entries
        """
        with self._lock:
            return len(self._cache)

    def _maybe_cleanup_expired(self) -> None:
        """Remove expired entries if cleanup interval has passed.

        This method is called internally and modifies cache state
        in a thread-safe manner.
        """
        now = time.time()
        if now - self._last_cleanup < self._config.check_expired_interval:
            return

        self._last_cleanup = now
        expired_keys = [key for key, entry in self._cache.items() if entry.is_expired()]

        for key in expired_keys:
            del self._cache[key]
            if self._config.enable_stats:
                self._stats = self._stats.with_expiration()


def create_cache_key(*args: object, **kwargs: object) -> str:
    """Create deterministic cache key from arguments.

    Pure function that generates a consistent hash key from
    arbitrary arguments and keyword arguments.

    Args:
        *args: Positional arguments to include in key
        **kwargs: Keyword arguments to include in key

    Returns:
        SHA256 hash of the serialized arguments

    Example:
        >>> key = create_cache_key("user", 123, role="admin")
        >>> assert key == create_cache_key("user", 123, role="admin")
    """
    return FunctionalCache._make_key(*args, **kwargs)  # noqa: SLF001
