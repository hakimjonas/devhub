"""Tests for the immutable caching layer.

This module tests the FunctionalCache implementation including TTL support,
LRU eviction, thread safety, and statistics tracking.
"""

import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from freezegun import freeze_time
from hypothesis import given
from hypothesis import strategies as st
from returns.result import Failure
from returns.result import Success

from devhub.cache import CacheConfig
from devhub.cache import CacheEntry
from devhub.cache import CacheStats
from devhub.cache import FunctionalCache
from devhub.cache import create_cache_key


class TestCacheEntry:
    """Test immutable CacheEntry dataclass."""

    def test_cache_entry_creation(self) -> None:
        """Test creating a cache entry."""
        entry = CacheEntry(
            value="test_value",
            expires_at=time.time() + 60,
            created_at=time.time(),
        )
        assert entry.value == "test_value"
        assert entry.access_count == 1
        assert not entry.is_expired()

    def test_cache_entry_immutability(self) -> None:
        """Test that cache entries are immutable."""
        entry = CacheEntry(
            value="test",
            expires_at=time.time() + 60,
            created_at=time.time(),
        )
        with pytest.raises(AttributeError):
            entry.value = "modified"  # type: ignore[misc]

    def test_cache_entry_expiration(self) -> None:
        """Test cache entry expiration check."""
        past_time = time.time() - 60
        expired_entry = CacheEntry(
            value="old",
            expires_at=past_time,
            created_at=past_time - 120,
        )
        assert expired_entry.is_expired()

        future_time = time.time() + 60
        valid_entry = CacheEntry(
            value="new",
            expires_at=future_time,
            created_at=time.time(),
        )
        assert not valid_entry.is_expired()

    def test_cache_entry_with_access(self) -> None:
        """Test creating new entry with incremented access count."""
        original = CacheEntry(
            value="test",
            expires_at=time.time() + 60,
            created_at=time.time(),
            access_count=5,
        )
        updated = original.with_access()

        assert updated.value == original.value
        assert updated.access_count == 6
        assert updated.last_accessed > original.last_accessed
        assert original.access_count == 5  # Original unchanged


class TestCacheStats:
    """Test immutable CacheStats dataclass."""

    def test_cache_stats_creation(self) -> None:
        """Test creating cache statistics."""
        stats = CacheStats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.hit_rate == 0.0

    def test_cache_stats_immutability(self) -> None:
        """Test that cache stats are immutable."""
        stats = CacheStats(hits=10, misses=5)
        with pytest.raises(AttributeError):
            stats.hits = 20  # type: ignore[misc]

    def test_cache_stats_hit_rate(self) -> None:
        """Test cache hit rate calculation."""
        stats = CacheStats(hits=75, misses=25, total_requests=100)
        assert stats.hit_rate == 75.0

        empty_stats = CacheStats()
        assert empty_stats.hit_rate == 0.0

    def test_cache_stats_updates(self) -> None:
        """Test updating cache statistics immutably."""
        original = CacheStats()

        after_hit = original.with_hit()
        assert after_hit.hits == 1
        assert after_hit.total_requests == 1
        assert original.hits == 0  # Original unchanged

        after_miss = after_hit.with_miss()
        assert after_miss.misses == 1
        assert after_miss.total_requests == 2

        after_eviction = after_miss.with_eviction()
        assert after_eviction.evictions == 1

        after_expiration = after_eviction.with_expiration()
        assert after_expiration.expirations == 1


class TestCacheConfig:
    """Test immutable CacheConfig dataclass."""

    def test_cache_config_defaults(self) -> None:
        """Test default cache configuration."""
        config = CacheConfig()
        assert config.max_size == 1000
        assert config.default_ttl_seconds == 300
        assert config.check_expired_interval == 60
        assert config.enable_stats is True

    def test_cache_config_custom(self) -> None:
        """Test custom cache configuration."""
        config = CacheConfig(
            max_size=50,
            default_ttl_seconds=60,
            enable_stats=False,
        )
        assert config.max_size == 50
        assert config.default_ttl_seconds == 60
        assert config.enable_stats is False

    def test_cache_config_immutability(self) -> None:
        """Test that cache config is immutable."""
        config = CacheConfig()
        with pytest.raises(AttributeError):
            config.max_size = 2000  # type: ignore[misc]


class TestFunctionalCache:
    """Test FunctionalCache implementation."""

    def test_cache_basic_operations(self) -> None:
        """Test basic cache get and put operations."""
        cache: FunctionalCache[str] = FunctionalCache(CacheConfig(max_size=10, default_ttl_seconds=60))

        # Test put and get
        put_result = cache.put("key1", "value1")
        assert isinstance(put_result, Success)

        get_result = cache.get("key1")
        assert isinstance(get_result, Success)
        assert get_result.unwrap() == "value1"

        # Test cache miss
        miss_result = cache.get("nonexistent")
        assert isinstance(miss_result, Failure)
        assert "miss" in str(miss_result)

    def test_cache_ttl_expiration(self) -> None:
        """Test cache TTL expiration."""
        cache: FunctionalCache[str] = FunctionalCache(CacheConfig(default_ttl_seconds=1))

        cache.put("temp_key", "temp_value", ttl_seconds=1)

        # Should be available immediately
        result = cache.get("temp_key")
        assert isinstance(result, Success)

        # Wait for expiration
        time.sleep(1.1)

        # Should be expired now
        result = cache.get("temp_key")
        assert isinstance(result, Failure)
        assert "expired" in str(result)

    def test_cache_lru_eviction(self) -> None:
        """Test LRU eviction when cache is full."""
        cache: FunctionalCache[int] = FunctionalCache(CacheConfig(max_size=3))

        # Fill cache
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)

        # Access 'a' to make it recently used
        cache.get("a")

        # Add new item, should evict 'b' (least recently used)
        cache.put("d", 4)

        # Check that 'b' was evicted
        assert isinstance(cache.get("b"), Failure)
        assert isinstance(cache.get("a"), Success)
        assert isinstance(cache.get("c"), Success)
        assert isinstance(cache.get("d"), Success)

    def test_cache_get_or_compute(self) -> None:
        """Test get_or_compute functionality."""
        cache: FunctionalCache[str] = FunctionalCache()
        compute_calls = 0

        def expensive_compute() -> str:
            nonlocal compute_calls
            compute_calls += 1
            return f"computed_{compute_calls}"

        # First call should compute
        result1 = cache.get_or_compute("key", expensive_compute)
        assert isinstance(result1, Success)
        assert result1.unwrap() == "computed_1"
        assert compute_calls == 1

        # Second call should use cache
        result2 = cache.get_or_compute("key", expensive_compute)
        assert isinstance(result2, Success)
        assert result2.unwrap() == "computed_1"
        assert compute_calls == 1  # Not called again

    def test_cache_invalidation(self) -> None:
        """Test cache invalidation."""
        cache: FunctionalCache[str] = FunctionalCache()

        cache.put("key1", "value1")
        cache.put("key2", "value2")

        # Invalidate one key
        result = cache.invalidate("key1")
        assert isinstance(result, Success)

        assert isinstance(cache.get("key1"), Failure)
        assert isinstance(cache.get("key2"), Success)

        # Invalidating non-existent key should succeed
        result = cache.invalidate("nonexistent")
        assert isinstance(result, Success)

    def test_cache_clear(self) -> None:
        """Test clearing entire cache."""
        cache: FunctionalCache[str] = FunctionalCache()

        cache.put("key1", "value1")
        cache.put("key2", "value2")
        assert cache.size() == 2

        result = cache.clear()
        assert isinstance(result, Success)
        assert cache.size() == 0
        assert isinstance(cache.get("key1"), Failure)
        assert isinstance(cache.get("key2"), Failure)

    def test_cache_statistics(self) -> None:
        """Test cache statistics tracking."""
        cache: FunctionalCache[str] = FunctionalCache(CacheConfig(enable_stats=True))

        cache.put("key1", "value1")
        cache.get("key1")  # Hit
        cache.get("key2")  # Miss

        stats = cache.get_stats()
        assert stats.hits == 1
        assert stats.misses == 1
        assert stats.total_requests == 2
        assert stats.hit_rate == 50.0

    def test_cache_thread_safety(self) -> None:
        """Test cache thread safety with concurrent operations."""
        cache: FunctionalCache[int] = FunctionalCache(CacheConfig(max_size=100))

        def cache_operations(thread_id: int) -> None:
            for i in range(10):
                key = f"thread_{thread_id}_item_{i}"
                cache.put(key, thread_id * 100 + i)
                cache.get(key)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(cache_operations, i) for i in range(10)]
            for future in futures:
                future.result()

        # Cache should have handled all operations safely
        assert cache.size() <= 100

    def test_cache_compute_error_handling(self) -> None:
        """Test error handling in get_or_compute."""
        cache: FunctionalCache[str] = FunctionalCache()

        def failing_compute() -> str:
            msg = "Computation failed"
            raise ValueError(msg)

        result = cache.get_or_compute("key", failing_compute)
        assert isinstance(result, Failure)
        assert "Failed to compute" in str(result)


class TestCreateCacheKey:
    """Test cache key generation."""

    def test_create_cache_key_deterministic(self) -> None:
        """Test that cache keys are deterministic."""
        key1 = create_cache_key("user", 123, role="admin")
        key2 = create_cache_key("user", 123, role="admin")
        assert key1 == key2

    def test_create_cache_key_different_args(self) -> None:
        """Test that different args produce different keys."""
        key1 = create_cache_key("user", 123)
        key2 = create_cache_key("user", 124)
        key3 = create_cache_key("admin", 123)

        assert key1 != key2
        assert key1 != key3
        assert key2 != key3

    def test_create_cache_key_kwargs_order(self) -> None:
        """Test that kwargs order doesn't affect key."""
        key1 = create_cache_key(a=1, b=2, c=3)
        key2 = create_cache_key(c=3, a=1, b=2)
        assert key1 == key2

    @given(
        st.lists(st.text(min_size=1)),
        st.dictionaries(st.text(min_size=1), st.integers()),
    )
    def test_create_cache_key_property(
        self,
        args: list[str],
        kwargs: dict[str, int],
    ) -> None:
        """Property-based test for cache key generation."""
        key1 = create_cache_key(*args, **kwargs)
        key2 = create_cache_key(*args, **kwargs)

        # Keys should be deterministic
        assert key1 == key2

        # Keys should be valid hex strings (SHA256)
        assert len(key1) == 64
        assert all(c in "0123456789abcdef" for c in key1)


class TestCacheIntegration:
    """Integration tests for cache with real use cases."""

    def test_cache_with_bundle_data(self) -> None:
        """Test caching bundle data structures."""
        from devhub.main import JiraIssue

        cache: FunctionalCache[JiraIssue] = FunctionalCache()

        issue = JiraIssue(
            key="PROJ-123",
            summary="Test Issue",
            description="Test description",
            raw_data={},
        )

        cache.put("PROJ-123", issue)
        result = cache.get("PROJ-123")

        assert isinstance(result, Success)
        cached_issue = result.unwrap()
        assert cached_issue.key == "PROJ-123"
        assert cached_issue.summary == "Test Issue"

    @freeze_time("2024-01-01 12:00:00")
    def test_cache_time_based_operations(self) -> None:
        """Test cache operations with frozen time."""
        cache: FunctionalCache[str] = FunctionalCache(CacheConfig(default_ttl_seconds=300))

        cache.put("key", "value")

        # Move forward but within TTL
        with freeze_time("2024-01-01 12:04:00"):
            result = cache.get("key")
            assert isinstance(result, Success)

        # Move beyond TTL
        with freeze_time("2024-01-01 12:06:00"):
            result = cache.get("key")
            assert isinstance(result, Failure)
