"""Additional tests to improve code coverage across all modules.

This module contains tests specifically designed to cover edge cases
and error paths that were missing from the original test suite.
"""

import json
import time
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from freezegun import freeze_time
from hypothesis import given
from hypothesis import strategies as st
from returns.result import Failure
from returns.result import Result
from returns.result import Success

from devhub.cache import CacheConfig
from devhub.cache import CacheStats
from devhub.cache import FunctionalCache
from devhub.cache import create_cache_key
from devhub.config import DevHubConfig
from devhub.config import GitHubConfig
from devhub.config import create_example_config
from devhub.config import export_config_to_dict
from devhub.config import load_config_file
from devhub.config import load_config_with_environment
from devhub.config import parse_config_data
from devhub.main import BundleData
from devhub.main import JiraIssue
from devhub.main import OutputPaths
from devhub.main import Repository
from devhub.main import ReviewComment
from devhub.main import extract_jira_key_from_branch
from devhub.main import format_json_output
from devhub.main import get_current_branch
from devhub.main import get_repository_info
from devhub.main import now_slug
from devhub.main import write_json_file
from devhub.mcp_server import DevHubMCPServer
from devhub.resilience import CircuitBreakerState
from devhub.resilience import CircuitState
from devhub.resilience import RetryPolicy
from devhub.resilience import RetryState
from devhub.resilience import async_with_retry
from devhub.sdk import DevHubAsyncClient
from devhub.sdk import DevHubClient
from devhub.sdk import SDKConfig
from devhub.sdk import StreamUpdate


class TestCacheEdgeCases:
    """Test edge cases in cache module."""

    def test_cache_cleanup_expired_multiple(self) -> None:
        """Test cleanup of multiple expired entries."""
        cache: FunctionalCache[str] = FunctionalCache(
            CacheConfig(
                max_size=5,
                default_ttl_seconds=1,
                check_expired_interval=1,
            )
        )

        # Add entries that will expire
        for i in range(3):
            cache.put(f"key{i}", f"value{i}", ttl_seconds=1)

        time.sleep(0.1)

        # Force cleanup by accessing cache
        cache.get("key0")

        # All should be expired
        assert cache.size() == 0

    def test_cache_stats_operations(self) -> None:
        """Test all cache stats operations."""
        stats = CacheStats()

        # Test all update methods
        stats = stats.with_hit()
        assert stats.hits == 1

        stats = stats.with_miss()
        assert stats.misses == 1

        stats = stats.with_eviction()
        assert stats.evictions == 1

        stats = stats.with_expiration()
        assert stats.expirations == 1

        assert stats.total_requests == 2  # hits + misses

    def test_cache_entry_access_tracking(self) -> None:
        """Test cache entry access count tracking."""
        cache: FunctionalCache[str] = FunctionalCache(CacheConfig(enable_stats=True))

        cache.put("key", "value")

        # Access multiple times
        for _ in range(5):
            cache.get("key")

        # Entry should track accesses internally
        assert cache.get_stats().hits == 5


class TestConfigEdgeCases:
    """Test edge cases in config module."""

    def test_config_get_organization_not_found(self) -> None:
        """Test getting non-existent organization."""
        config = DevHubConfig()
        assert config.get_organization("nonexistent") is None

    def test_config_get_default_organization_empty(self) -> None:
        """Test getting default org when none configured."""
        config = DevHubConfig()
        assert config.get_default_organization() is None

    def test_config_get_effective_github_config_no_org(self) -> None:
        """Test effective GitHub config with no org."""
        config = DevHubConfig(global_github=GitHubConfig(default_org="global-org"))
        github = config.get_effective_github_config()
        assert github.default_org == "global-org"

    def test_parse_config_data_minimal(self) -> None:
        """Test parsing minimal config data."""
        result = parse_config_data({})
        assert isinstance(result, Success)
        config = result.unwrap()
        assert config.config_version == "1.0"

    def test_parse_config_data_with_organizations(self) -> None:
        """Test parsing config with organizations."""
        data = {
            "organizations": [
                {
                    "name": "test-org",
                    "description": "Test organization",
                    "jira": {"default_project_prefix": "TEST"},
                }
            ]
        }
        result = parse_config_data(data)
        assert isinstance(result, Success)
        config = result.unwrap()
        assert len(config.organizations) == 1
        assert config.organizations[0].name == "test-org"

    def test_load_config_file_not_found(self) -> None:
        """Test loading non-existent config file."""
        result = load_config_file(Path("/nonexistent/config.toml"))
        assert isinstance(result, Failure)

    def test_load_config_with_environment_custom_path(self) -> None:
        """Test loading config from custom path."""
        with patch("devhub.config.load_config_file") as mock_load:
            mock_load.return_value = Success({})
            result = load_config_with_environment("/custom/path.toml")
            assert isinstance(result, Success)
            mock_load.assert_called_once()

    def test_export_config_to_dict(self) -> None:
        """Test exporting config to dictionary."""
        config = create_example_config()
        exported = export_config_to_dict(config)
        assert "organizations" in exported
        assert "jira" in exported
        assert "github" in exported
        assert "output" in exported
        assert "config_version" in exported


class TestMainEdgeCases:
    """Test edge cases in main module."""

    def test_output_paths_methods(self) -> None:
        """Test all OutputPaths methods."""
        base = Path("/test/output")
        paths = OutputPaths(base)

        assert paths.jira_json("TEST-123") == base / "jira_TEST-123.json"
        assert paths.jira_md("TEST-123") == base / "jira_TEST-123.md"
        assert paths.pr_json(456) == base / "pr_456.json"
        assert paths.pr_md(456) == base / "pr_456.md"
        assert paths.pr_diff(456) == base / "pr_456.diff"
        assert paths.comments_json(456) == base / "unresolved_comments_pr456.json"

    def test_bundle_data_to_dict_without_content(self) -> None:
        """Test BundleData to_dict without content."""
        bundle = BundleData(
            repository=Repository(owner="test", name="repo"),
            branch="main",
            jira_issue=JiraIssue(
                key="TEST-1",
                summary="Test",
                description="Desc",
                raw_data={},
            ),
            pr_data={"number": 1},
            pr_diff="diff content",
            comments=(
                ReviewComment(
                    id="1",
                    body="comment",
                    path=None,
                    author="user",
                    created_at="2024-01-01",
                    diff_hunk=None,
                    resolved=False,
                ),
            ),
        )

        result = bundle.to_dict(include_content=False)
        assert "metadata" in result
        assert "repository" in result["metadata"]
        assert "pr_diff" not in result

    def test_format_json_output_pretty(self) -> None:
        """Test JSON formatting with pretty print."""
        data = {"key": "value", "nested": {"a": 1, "b": 2}}
        formatted = format_json_output(data, "json")
        parsed = json.loads(formatted)
        assert parsed == data

    def test_now_slug(self) -> None:
        """Test timestamp slug generation."""
        with freeze_time("2024-01-15 10:30:45"):
            slug = now_slug()
            assert slug == "20240115-103045"

    def test_extract_jira_key_patterns(self) -> None:
        """Test various JIRA key extraction patterns."""
        assert extract_jira_key_from_branch("feature/TEST-123") == "TEST-123"
        assert extract_jira_key_from_branch("TEST-456-description") == "TEST-456"
        assert extract_jira_key_from_branch("bugfix/PROJ-789-fix") == "PROJ-789"
        assert extract_jira_key_from_branch("no-jira-key") is None

    @patch("subprocess.run")
    def test_get_current_branch_failure(self, mock_run: Mock) -> None:
        """Test getting current branch when git fails."""
        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="not a git repository",
        )
        result = get_current_branch()
        assert isinstance(result, Failure)

    @patch("subprocess.run")
    def test_get_repository_info_failure(self, mock_run: Mock) -> None:
        """Test getting repo info when gh fails."""
        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="error",
        )
        result = get_repository_info()
        assert isinstance(result, Failure)

    def test_write_json_file(self) -> None:
        """Test writing JSON file."""
        with patch("pathlib.Path.write_text") as mock_write:
            mock_write.return_value = None
            data = {"test": "data"}
            result = write_json_file(Path("/test/file.json"), data)
            assert isinstance(result, Success)
            mock_write.assert_called_once_with('{\n  "test": "data"\n}', encoding="utf-8")


class TestResilienceEdgeCases:
    """Test edge cases in resilience module."""

    def test_retry_state_tracking(self) -> None:
        """Test retry state progression."""
        state = RetryState()
        assert state.attempt == 0

        state = state.next_attempt(1.5, ValueError("test"))
        assert state.attempt == 1
        assert state.total_delay == 1.5
        assert isinstance(state.last_exception, ValueError)

    def test_circuit_breaker_state_half_open_success(self) -> None:
        """Test circuit breaker success in half-open state."""
        state = CircuitBreakerState(state=CircuitState.HALF_OPEN)
        new_state = state.with_success()
        assert new_state.success_count == 1
        assert new_state.failure_count == 0

    def test_circuit_breaker_state_closed_success(self) -> None:
        """Test circuit breaker success in closed state."""
        state = CircuitBreakerState(state=CircuitState.CLOSED)
        new_state = state.with_success()
        assert new_state.success_count == 0
        assert new_state.failure_count == 0

    def test_circuit_breaker_should_not_transition(self) -> None:
        """Test circuit breaker should not transition when not open."""
        state = CircuitBreakerState(state=CircuitState.CLOSED)
        assert not state.should_transition_to_half_open(60.0)

    @pytest.mark.asyncio
    async def test_async_retry_with_immediate_success(self) -> None:
        """Test async retry with immediate success."""

        async def operation() -> Result[str, str]:
            return Success("immediate")

        result = await async_with_retry(operation)
        assert isinstance(result, Success)
        assert result.unwrap() == "immediate"


class TestSDKEdgeCases:
    """Test edge cases in SDK module."""

    @pytest.mark.asyncio
    async def test_devhub_client_cache_hit(self) -> None:
        """Test DevHubClient cache hit path."""
        client = DevHubClient(SDKConfig(cache_enabled=True))
        await client.initialize()

        with patch.object(client, "_check_cache") as mock_cache:
            mock_cache.return_value = Success(
                BundleData(
                    repository=Repository(owner="test", name="repo"),
                    branch="main",
                )
            )

            result = await client.get_bundle_context()
            assert isinstance(result, Success)
            mock_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_devhub_client_initialization_failure(self) -> None:
        """Test DevHubClient initialization failure."""
        client = DevHubClient()

        with patch("devhub.sdk.load_config_with_environment") as mock_load:
            mock_load.side_effect = ValueError("config error")
            result = await client.initialize()
            assert isinstance(result, Failure)

    def test_stream_update_creation(self) -> None:
        """Test StreamUpdate dataclass."""
        update = StreamUpdate(
            update_type="pr_updated",
            data={"pr_number": 123},
            timestamp="2024-01-01T00:00:00Z",
        )
        assert update.update_type == "pr_updated"
        assert update.data["pr_number"] == 123

    @pytest.mark.asyncio
    async def test_devhub_async_client_basic(self) -> None:
        """Test DevHubAsyncClient basic functionality."""
        client = DevHubAsyncClient()

        with patch("devhub.sdk.load_config_with_environment") as mock_load:
            mock_load.return_value = Success(DevHubConfig())
            result = await client._client.initialize()
            assert isinstance(result, Success)


class TestMCPServerEdgeCases:
    """Test edge cases in MCP server module."""

    @pytest.mark.asyncio
    async def test_mcp_server_unknown_tool(self) -> None:
        """Test MCP server handling unknown tool."""
        server = DevHubMCPServer()

        result = await server.handle_request(
            {
                "method": "tools/call",
                "params": {"name": "unknown_tool", "arguments": {}},
            }
        )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_mcp_server_get_jira_issue_no_creds(self) -> None:
        """Test get_jira_issue without credentials."""
        server = DevHubMCPServer()

        with patch("devhub.mcp_server.get_jira_credentials_from_config") as mock:
            mock.return_value = Failure("No credentials")

            result = await server._get_jira_issue("TEST-1")
            assert isinstance(result, dict)
            assert "error" in result

    @pytest.mark.asyncio
    async def test_mcp_server_initialization(self) -> None:
        """Test MCP server initialization."""
        server = DevHubMCPServer()
        # MCP server doesn't need explicit initialization
        assert server is not None


# Property-based tests for additional coverage
class TestPropertyBased:
    """Property-based tests for edge cases."""

    @given(
        st.text(min_size=1, max_size=10),
        st.integers(min_value=1, max_value=1000),
    )
    def test_cache_key_consistency(self, text: str, number: int) -> None:
        """Test cache key generation consistency."""
        key1 = create_cache_key(text, number, flag=True)
        key2 = create_cache_key(text, number, flag=True)
        assert key1 == key2
        assert len(key1) == 64  # SHA256 hex length

    @given(st.integers(min_value=0, max_value=10))
    def test_retry_delay_calculation(self, attempt: int) -> None:
        """Test retry delay calculation properties."""
        policy = RetryPolicy(
            base_delay=1.0,
            exponential_base=2.0,
            max_delay=100.0,
            jitter=False,
        )

        delay = policy.calculate_delay(attempt)

        if attempt == 0:
            assert delay == 0
        else:
            expected = min(1.0 * (2.0 ** (attempt - 1)), 100.0)
            assert delay == expected

    @given(
        st.text(min_size=1, max_size=20),
        st.text(min_size=1, max_size=20),
    )
    def test_jira_key_extraction_property(
        self,
        prefix: str,
        suffix: str,
    ) -> None:
        """Test JIRA key extraction with various inputs."""
        # Only test with valid prefixes (uppercase letters)
        if prefix.isupper() and suffix.isdigit():
            branch = f"feature/{prefix}-{suffix}"
            result = extract_jira_key_from_branch(branch)
            if len(prefix) >= 2 and len(prefix) <= 10:
                assert result == f"{prefix}-{suffix}"
