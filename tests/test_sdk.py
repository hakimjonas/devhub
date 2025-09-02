"""Comprehensive tests for DevHub SDK module."""

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from returns.result import Failure, Success

from devhub.config import DevHubConfig
from devhub.main import BundleData, JiraIssue, Repository, ReviewComment
from devhub.sdk import (
    ContextRequest,
    DevHubAsyncClient,
    DevHubClient,
    SDKConfig,
    StreamUpdate,
    get_context_for_jira,
    get_context_for_pr,
    get_current_context,
)


class TestSDKConfig:
    """Test SDKConfig dataclass."""

    def test_sdk_config_defaults(self):
        """Test default values."""
        config = SDKConfig()
        assert config.workspace_path == Path.cwd()
        assert config.organization is None
        assert config.cache_enabled is True
        assert config.cache_ttl_seconds == 300
        assert config.timeout_seconds == 30

    def test_sdk_config_custom_values(self):
        """Test custom values."""
        config = SDKConfig(
            workspace_path=Path("/custom"),
            organization="test-org",
            cache_enabled=False,
            cache_ttl_seconds=600,
            timeout_seconds=60,
        )
        assert config.workspace_path == Path("/custom")
        assert config.organization == "test-org"
        assert config.cache_enabled is False
        assert config.cache_ttl_seconds == 600
        assert config.timeout_seconds == 60

    def test_sdk_config_immutable(self):
        """Test that SDKConfig is immutable."""
        config = SDKConfig()
        with pytest.raises(AttributeError):
            config.workspace_path = Path("/new")


class TestContextRequest:
    """Test ContextRequest dataclass."""

    def test_context_request_defaults(self):
        """Test default values."""
        request = ContextRequest()
        assert request.jira_key is None
        assert request.pr_number is None
        assert request.branch is None
        assert request.include_jira is True
        assert request.include_pr is True
        assert request.include_diff is True
        assert request.include_comments is True
        assert request.comment_limit == 20
        assert request.metadata_only is False

    def test_context_request_custom_values(self):
        """Test custom values."""
        request = ContextRequest(
            jira_key="TEST-123",
            pr_number=456,
            branch="feature/test",
            include_jira=False,
            include_pr=False,
            include_diff=False,
            include_comments=False,
            comment_limit=50,
            metadata_only=True,
        )
        assert request.jira_key == "TEST-123"
        assert request.pr_number == 456
        assert request.branch == "feature/test"
        assert request.include_jira is False
        assert request.include_pr is False
        assert request.include_diff is False
        assert request.include_comments is False
        assert request.comment_limit == 50
        assert request.metadata_only is True

    def test_context_request_immutable(self):
        """Test that ContextRequest is immutable."""
        request = ContextRequest()
        with pytest.raises(AttributeError):
            request.jira_key = "NEW-123"


class TestStreamUpdate:
    """Test StreamUpdate dataclass."""

    def test_stream_update_creation(self):
        """Test StreamUpdate creation."""
        update = StreamUpdate(
            update_type="pr_updated",
            data={"id": 123, "title": "Test PR"},
            timestamp="2023-01-01T00:00:00Z",
        )
        assert update.update_type == "pr_updated"
        assert update.data == {"id": 123, "title": "Test PR"}
        assert update.timestamp == "2023-01-01T00:00:00Z"

    def test_stream_update_immutable(self):
        """Test that StreamUpdate is immutable."""
        update = StreamUpdate("test", {}, "2023-01-01T00:00:00Z")
        with pytest.raises(AttributeError):
            update.update_type = "new_type"


class TestDevHubClient:
    """Test DevHubClient class."""

    def test_client_initialization_default(self):
        """Test client initialization with default config."""
        client = DevHubClient()
        assert client._config.workspace_path == Path.cwd()
        assert client._devhub_config is None
        assert client._cache == {}

    def test_client_initialization_custom_config(self):
        """Test client initialization with custom config."""
        config = SDKConfig(organization="test-org")
        client = DevHubClient(config)
        assert client._config.organization == "test-org"

    @pytest.mark.asyncio
    async def test_initialize_success(self):
        """Test successful initialization."""
        client = DevHubClient()

        with patch("devhub.sdk.load_config_with_environment") as mock_load:
            mock_config = DevHubConfig()
            mock_load.return_value = Success(mock_config)

            result = await client.initialize()

            assert isinstance(result, Success)
            assert client._devhub_config == mock_config

    @pytest.mark.asyncio
    async def test_initialize_config_failure(self):
        """Test initialization with config loading failure."""
        client = DevHubClient()

        with patch("devhub.sdk.load_config_with_environment") as mock_load:
            mock_load.return_value = Failure("Config error")

            result = await client.initialize()

            assert isinstance(result, Success)  # Should still succeed with default config
            assert isinstance(client._devhub_config, DevHubConfig)

    @pytest.mark.asyncio
    async def test_initialize_exception(self):
        """Test initialization with exception."""
        client = DevHubClient()

        with patch("devhub.sdk.load_config_with_environment") as mock_load:
            mock_load.side_effect = ValueError("Test error")

            result = await client.initialize()

            assert isinstance(result, Failure)
            assert "Failed to initialize DevHub client" in result.failure()

    @pytest.mark.asyncio
    async def test_get_bundle_context_not_initialized(self):
        """Test get_bundle_context when not initialized."""
        client = DevHubClient()

        with patch.object(client, "initialize") as mock_init:
            mock_init.return_value = Failure("Init error")

            result = await client.get_bundle_context()

            assert isinstance(result, Failure)
            assert result.failure() == "Init error"

    @pytest.mark.asyncio
    async def test_get_bundle_context_with_cache(self):
        """Test get_bundle_context with cached result."""
        config = SDKConfig(cache_enabled=True)
        client = DevHubClient(config)
        client._devhub_config = DevHubConfig()

        # Setup cache
        mock_bundle_data = BundleData(
            jira_issue=None,
            pr_data=None,
            pr_diff=None,
            comments=(),
            repository=Repository(owner="test", name="repo"),
            branch="main",
            metadata={},
        )

        request = ContextRequest()
        cache_key = f"bundle_{hash(str(request))}"
        client._cache[cache_key] = (time.time(), mock_bundle_data)

        result = await client.get_bundle_context(request)

        assert isinstance(result, Success)
        assert result.unwrap() == mock_bundle_data

    @pytest.mark.asyncio
    async def test_get_bundle_context_cache_disabled(self):
        """Test get_bundle_context with cache disabled."""
        config = SDKConfig(cache_enabled=False)
        client = DevHubClient(config)
        client._devhub_config = DevHubConfig()

        with patch.object(client, "_build_bundle_context") as mock_build:
            mock_bundle_data = BundleData(
                jira_issue=None,
                pr_data=None,
                pr_diff=None,
                comments=(),
                repository=Repository(owner="test", name="repo"),
                branch="main",
                metadata={},
            )
            mock_build.return_value = Success(mock_bundle_data)

            result = await client.get_bundle_context()

            assert isinstance(result, Success)
            mock_build.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_bundle_context_exception(self):
        """Test get_bundle_context with exception."""
        client = DevHubClient()
        client._devhub_config = DevHubConfig()

        with patch.object(client, "_build_bundle_context") as mock_build:
            mock_build.side_effect = ValueError("Test error")

            result = await client.get_bundle_context()

            assert isinstance(result, Failure)
            assert "Failed to get bundle context: Test error" in result.failure()

    def test_get_repo_and_branch_success(self):
        """Test _get_repo_and_branch success."""
        client = DevHubClient()
        request = ContextRequest(branch="feature/test")

        mock_repo = Repository(owner="test", name="repo")

        with patch("devhub.sdk.get_repository_info") as mock_get_repo:
            mock_get_repo.return_value = Success(mock_repo)

            result = client._get_repo_and_branch(request)

            assert isinstance(result, Success)
            repo, branch = result.unwrap()
            assert repo == mock_repo
            assert branch == "feature/test"

    def test_get_repo_and_branch_auto_detect_branch(self):
        """Test _get_repo_and_branch with auto-detected branch."""
        client = DevHubClient()
        request = ContextRequest()  # No branch specified

        mock_repo = Repository(owner="test", name="repo")

        with patch("devhub.sdk.get_repository_info") as mock_get_repo, \
             patch("devhub.sdk.get_current_branch") as mock_get_branch:
            mock_get_repo.return_value = Success(mock_repo)
            mock_get_branch.return_value = Success("main")

            result = client._get_repo_and_branch(request)

            assert isinstance(result, Success)
            repo, branch = result.unwrap()
            assert repo == mock_repo
            assert branch == "main"

    def test_get_repo_and_branch_repo_failure(self):
        """Test _get_repo_and_branch with repository failure."""
        client = DevHubClient()
        request = ContextRequest()

        with patch("devhub.sdk.get_repository_info") as mock_get_repo:
            mock_get_repo.return_value = Failure("Repo error")

            result = client._get_repo_and_branch(request)

            assert isinstance(result, Failure)
            assert result.failure() == "Repo error"

    def test_get_repo_and_branch_branch_failure(self):
        """Test _get_repo_and_branch with branch detection failure."""
        client = DevHubClient()
        request = ContextRequest()  # No branch specified

        mock_repo = Repository(owner="test", name="repo")

        with patch("devhub.sdk.get_repository_info") as mock_get_repo, \
             patch("devhub.sdk.get_current_branch") as mock_get_branch:
            mock_get_repo.return_value = Success(mock_repo)
            mock_get_branch.return_value = Failure("Branch error")

            result = client._get_repo_and_branch(request)

            assert isinstance(result, Failure)
            assert result.failure() == "Branch error"

    def test_resolve_identifiers_with_explicit_values(self):
        """Test _resolve_identifiers with explicit values."""
        client = DevHubClient()
        client._devhub_config = DevHubConfig()
        request = ContextRequest(jira_key="TEST-123", pr_number=456)
        repo = Repository(owner="test", name="repo")

        jira_key, pr_number = client._resolve_identifiers(request, "main", repo)

        assert jira_key == "TEST-123"
        assert pr_number == 456

    def test_resolve_identifiers_auto_resolve(self):
        """Test _resolve_identifiers with auto-resolution."""
        client = DevHubClient()
        client._devhub_config = DevHubConfig()
        client._config = SDKConfig(organization="test-org")
        request = ContextRequest()
        repo = Repository(owner="test", name="repo")

        with patch("devhub.sdk.resolve_jira_key_with_config") as mock_resolve_jira, \
             patch("devhub.sdk.resolve_pr_number") as mock_resolve_pr:
            mock_resolve_jira.return_value = "RESOLVED-123"
            mock_resolve_pr.return_value = Success(789)

            jira_key, pr_number = client._resolve_identifiers(request, "feature/test", repo)

            assert jira_key == "RESOLVED-123"
            assert pr_number == 789
            mock_resolve_jira.assert_called_once_with(
                client._devhub_config, branch="feature/test", org_name="test-org"
            )

    def test_resolve_identifiers_pr_resolution_failure(self):
        """Test _resolve_identifiers with PR resolution failure."""
        client = DevHubClient()
        client._devhub_config = DevHubConfig()
        request = ContextRequest()
        repo = Repository(owner="test", name="repo")

        with patch("devhub.sdk.resolve_jira_key_with_config") as mock_resolve_jira, \
             patch("devhub.sdk.resolve_pr_number") as mock_resolve_pr:
            mock_resolve_jira.return_value = "RESOLVED-123"
            mock_resolve_pr.return_value = Failure("PR not found")

            jira_key, pr_number = client._resolve_identifiers(request, "feature/test", repo)

            assert jira_key == "RESOLVED-123"
            assert pr_number is None

    def test_create_bundle_config(self):
        """Test _create_bundle_config."""
        client = DevHubClient()
        client._config = SDKConfig(organization="test-org")
        request = ContextRequest(
            include_jira=False,
            include_pr=True,
            include_diff=False,
            include_comments=True,
            comment_limit=50,
        )

        bundle_config = client._create_bundle_config(request)

        assert bundle_config.include_jira is False
        assert bundle_config.include_pr is True
        assert bundle_config.include_diff is False
        assert bundle_config.include_comments is True
        assert bundle_config.limit == 50
        assert bundle_config.organization == "test-org"

    def test_gather_data(self):
        """Test _gather_data."""
        client = DevHubClient()
        client._devhub_config = DevHubConfig()

        from devhub.main import BundleConfig
        bundle_config = BundleConfig()
        repo = Repository(owner="test", name="repo")

        with patch("devhub.sdk._gather_bundle_data") as mock_gather:
            mock_gather.return_value = Success('{"test": "data"}')

            result = client._gather_data(
                ContextRequest(), bundle_config, repo, "main", "TEST-123", 456
            )

            assert isinstance(result, Success)
            assert result.unwrap() == '{"test": "data"}'

    def test_process_result_success(self):
        """Test _process_result success."""
        config = SDKConfig(cache_enabled=True)
        client = DevHubClient(config)
        repo = Repository(owner="test", name="repo")
        request = ContextRequest()

        json_result = json.dumps({
            "jira": {
                "key": "TEST-123",
                "summary": "Test issue",
                "description": "Test description",
                "raw_data": {"id": "123"}
            },
            "pull_request": {"number": 456},
            "diff": "test diff",
            "comments": [
                {
                    "id": 1,
                    "body": "Test comment",
                    "path": "test.py",
                    "author": "testuser",
                    "created_at": "2023-01-01T00:00:00Z",
                    "diff_hunk": "@@ -1,3 +1,3 @@",
                    "resolved": False
                }
            ],
            "metadata": {"version": "1.0"}
        })

        result = client._process_result(json_result, repo, "main", request)

        assert isinstance(result, Success)
        bundle_data = result.unwrap()
        assert bundle_data.jira_issue.key == "TEST-123"
        assert bundle_data.pr_data == {"number": 456}
        assert bundle_data.pr_diff == "test diff"
        assert len(bundle_data.comments) == 1
        assert bundle_data.comments[0].body == "Test comment"
        assert bundle_data.repository == repo
        assert bundle_data.branch == "main"
        assert bundle_data.metadata == {"version": "1.0"}

    @pytest.mark.asyncio
    async def test_get_jira_issue_success(self):
        """Test get_jira_issue success."""
        client = DevHubClient()
        client._devhub_config = DevHubConfig()

        mock_jira_issue = JiraIssue(
            key="TEST-123",
            summary="Test issue",
            description="Test description",
            raw_data={}
        )

        with patch("devhub.sdk.get_jira_credentials_from_config") as mock_get_creds, \
             patch("devhub.sdk.fetch_jira_issue") as mock_fetch:
            mock_get_creds.return_value = ("user", "token", "https://test.atlassian.net")
            mock_fetch.return_value = Success(mock_jira_issue)

            result = await client.get_jira_issue("TEST-123")

            assert isinstance(result, Success)
            assert result.unwrap() == mock_jira_issue

    @pytest.mark.asyncio
    async def test_get_jira_issue_no_credentials(self):
        """Test get_jira_issue with no credentials."""
        client = DevHubClient()
        client._devhub_config = DevHubConfig()

        with patch("devhub.sdk.get_jira_credentials_from_config") as mock_get_creds, \
             patch("devhub.sdk.get_jira_credentials") as mock_get_env_creds:
            mock_get_creds.return_value = None
            mock_get_env_creds.return_value = None

            result = await client.get_jira_issue("TEST-123")

            assert isinstance(result, Failure)
            assert "Jira credentials not configured" in result.failure()

    @pytest.mark.asyncio
    async def test_get_jira_issue_exception(self):
        """Test get_jira_issue with exception."""
        client = DevHubClient()
        client._devhub_config = DevHubConfig()

        with patch("devhub.sdk.get_jira_credentials_from_config") as mock_get_creds:
            mock_get_creds.side_effect = ValueError("Test error")

            result = await client.get_jira_issue("TEST-123")

            assert isinstance(result, Failure)
            assert "Failed to get Jira issue: Test error" in result.failure()

    @pytest.mark.asyncio
    async def test_get_pr_details_success(self):
        """Test get_pr_details success."""
        client = DevHubClient()

        mock_repo = Repository(owner="test", name="repo")
        mock_pr_data = {"number": 123, "title": "Test PR"}
        mock_diff = "test diff content"

        with patch("devhub.sdk.get_repository_info") as mock_get_repo, \
             patch("devhub.sdk.fetch_pr_details") as mock_fetch_pr, \
             patch("devhub.sdk.fetch_pr_diff") as mock_fetch_diff:
            mock_get_repo.return_value = Success(mock_repo)
            mock_fetch_pr.return_value = Success(mock_pr_data.copy())
            mock_fetch_diff.return_value = Success(mock_diff)

            result = await client.get_pr_details(123, include_diff=True)

            assert isinstance(result, Success)
            pr_data = result.unwrap()
            assert pr_data["number"] == 123
            assert pr_data["diff"] == mock_diff

    @pytest.mark.asyncio
    async def test_get_pr_details_no_diff(self):
        """Test get_pr_details without diff."""
        client = DevHubClient()

        mock_repo = Repository(owner="test", name="repo")
        mock_pr_data = {"number": 123, "title": "Test PR"}

        with patch("devhub.sdk.get_repository_info") as mock_get_repo, \
             patch("devhub.sdk.fetch_pr_details") as mock_fetch_pr:
            mock_get_repo.return_value = Success(mock_repo)
            mock_fetch_pr.return_value = Success(mock_pr_data)

            result = await client.get_pr_details(123, include_diff=False)

            assert isinstance(result, Success)
            pr_data = result.unwrap()
            assert pr_data["number"] == 123
            assert "diff" not in pr_data

    @pytest.mark.asyncio
    async def test_get_pr_details_repo_failure(self):
        """Test get_pr_details with repository failure."""
        client = DevHubClient()

        with patch("devhub.sdk.get_repository_info") as mock_get_repo:
            mock_get_repo.return_value = Failure("Repo error")

            result = await client.get_pr_details(123)

            assert isinstance(result, Failure)
            assert result.failure() == "Repo error"

    @pytest.mark.asyncio
    async def test_get_pr_comments_success(self):
        """Test get_pr_comments success."""
        client = DevHubClient()

        mock_repo = Repository(owner="test", name="repo")
        mock_comments = (
            ReviewComment(
                id=1,
                body="Test comment",
                path="test.py",
                author="testuser",
                created_at="2023-01-01T00:00:00Z",
                diff_hunk="@@ -1,3 +1,3 @@",
                resolved=False
            ),
        )

        with patch("devhub.sdk.get_repository_info") as mock_get_repo, \
             patch("devhub.sdk.fetch_unresolved_comments") as mock_fetch_comments:
            mock_get_repo.return_value = Success(mock_repo)
            mock_fetch_comments.return_value = Success(mock_comments)

            result = await client.get_pr_comments(123, limit=50)

            assert isinstance(result, Success)
            comments = result.unwrap()
            assert len(comments) == 1
            assert comments[0].body == "Test comment"

    @pytest.mark.asyncio
    async def test_get_current_branch_context(self):
        """Test get_current_branch_context."""
        client = DevHubClient()

        with patch.object(client, "get_bundle_context") as mock_get_bundle:
            mock_bundle_data = BundleData(
                jira_issue=None,
                pr_data=None,
                pr_diff=None,
                comments=(),
                repository=Repository(owner="test", name="repo"),
                branch="main",
                metadata={},
            )
            mock_get_bundle.return_value = Success(mock_bundle_data)

            result = await client.get_current_branch_context(
                include_diff=False,
                include_comments=False,
                comment_limit=10
            )

            assert isinstance(result, Success)
            mock_get_bundle.assert_called_once()
            # Verify the ContextRequest was created correctly
            call_args = mock_get_bundle.call_args[0][0]
            assert call_args.include_diff is False
            assert call_args.include_comments is False
            assert call_args.comment_limit == 10

    @pytest.mark.asyncio
    async def test_stream_pr_updates(self):
        """Test stream_pr_updates."""
        client = DevHubClient()

        mock_pr_data = {
            "number": 123,
            "title": "Test PR",
            "updated_at": "2023-01-01T00:00:00Z"
        }

        with patch.object(client, "get_pr_details") as mock_get_pr, \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_get_pr.return_value = Success(mock_pr_data)

            # Create async generator and get first update
            stream = client.stream_pr_updates(123)
            update = await stream.__anext__()

            assert update.update_type == "pr_updated"
            assert update.data == mock_pr_data
            assert update.timestamp == "2023-01-01T00:00:00Z"

            # Stop the stream by raising StopAsyncIteration
            await stream.aclose()

    @pytest.mark.asyncio
    async def test_execute_cli_command_success(self):
        """Test execute_cli_command success."""
        client = DevHubClient()

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"output", b"")

        with patch("asyncio.create_subprocess_exec") as mock_create_process, \
             patch("asyncio.wait_for") as mock_wait:
            mock_create_process.return_value = mock_process
            mock_wait.return_value = (b"output", b"")

            result = await client.execute_cli_command(["bundle", "--help"])

            assert isinstance(result, Success)
            assert result.unwrap() == "output"

    @pytest.mark.asyncio
    async def test_execute_cli_command_failure(self):
        """Test execute_cli_command failure."""
        client = DevHubClient()

        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = (b"", b"error message")

        with patch("asyncio.create_subprocess_exec") as mock_create_process, \
             patch("asyncio.wait_for") as mock_wait:
            mock_create_process.return_value = mock_process
            mock_wait.return_value = (b"", b"error message")

            result = await client.execute_cli_command(["invalid", "command"])

            assert isinstance(result, Failure)
            assert "CLI command failed: error message" in result.failure()

    @pytest.mark.asyncio
    async def test_execute_cli_command_timeout(self):
        """Test execute_cli_command timeout."""
        client = DevHubClient()

        with patch("asyncio.create_subprocess_exec") as mock_create_process, \
             patch("asyncio.wait_for") as mock_wait:
            mock_create_process.return_value = AsyncMock()
            mock_wait.side_effect = TimeoutError()

            result = await client.execute_cli_command(["slow", "command"])

            assert isinstance(result, Failure)
            assert "CLI command timed out" in result.failure()

    def test_json_to_bundle_data_full(self):
        """Test _json_to_bundle_data with full data."""
        client = DevHubClient()
        repo = Repository(owner="test", name="repo")

        json_data = {
            "jira": {
                "key": "TEST-123",
                "summary": "Test issue",
                "description": "Test description",
                "raw_data": {"id": "123"}
            },
            "pull_request": {"number": 456},
            "diff": "test diff",
            "comments": [
                {
                    "id": 1,
                    "body": "Test comment",
                    "path": "test.py",
                    "author": "testuser",
                    "created_at": "2023-01-01T00:00:00Z",
                    "diff_hunk": "@@ -1,3 +1,3 @@",
                    "resolved": False
                }
            ],
            "metadata": {"version": "1.0"}
        }

        bundle_data = client._json_to_bundle_data(json_data, repo, "main")

        assert bundle_data.jira_issue.key == "TEST-123"
        assert bundle_data.jira_issue.summary == "Test issue"
        assert bundle_data.pr_data == {"number": 456}
        assert bundle_data.pr_diff == "test diff"
        assert len(bundle_data.comments) == 1
        assert bundle_data.comments[0].body == "Test comment"
        assert bundle_data.repository == repo
        assert bundle_data.branch == "main"
        assert bundle_data.metadata == {"version": "1.0"}

    def test_json_to_bundle_data_minimal(self):
        """Test _json_to_bundle_data with minimal data."""
        client = DevHubClient()
        repo = Repository(owner="test", name="repo")

        json_data = {}

        bundle_data = client._json_to_bundle_data(json_data, repo, "main")

        assert bundle_data.jira_issue is None
        assert bundle_data.pr_data is None
        assert bundle_data.pr_diff is None
        assert len(bundle_data.comments) == 0
        assert bundle_data.repository == repo
        assert bundle_data.branch == "main"
        assert bundle_data.metadata == {}

    def test_get_cached_result_cache_disabled(self):
        """Test _get_cached_result with cache disabled."""
        config = SDKConfig(cache_enabled=False)
        client = DevHubClient(config)

        result = client._get_cached_result("test", ContextRequest())

        assert result is None

    def test_get_cached_result_cache_miss(self):
        """Test _get_cached_result with cache miss."""
        config = SDKConfig(cache_enabled=True)
        client = DevHubClient(config)

        result = client._get_cached_result("test", ContextRequest())

        assert result is None

    def test_get_cached_result_cache_hit_valid(self):
        """Test _get_cached_result with valid cached data."""
        config = SDKConfig(cache_enabled=True, cache_ttl_seconds=300)
        client = DevHubClient(config)

        # Setup cache
        request = ContextRequest()
        cache_key = f"test_{hash(str(request))}"
        test_data = {"cached": "data"}
        client._cache[cache_key] = (time.time(), test_data)

        result = client._get_cached_result("test", request)

        assert result == test_data

    def test_get_cached_result_cache_expired(self):
        """Test _get_cached_result with expired cached data."""
        config = SDKConfig(cache_enabled=True, cache_ttl_seconds=300)
        client = DevHubClient(config)

        # Setup expired cache
        request = ContextRequest()
        cache_key = f"test_{hash(str(request))}"
        test_data = {"cached": "data"}
        client._cache[cache_key] = (time.time() - 400, test_data)  # Expired

        result = client._get_cached_result("test", request)

        assert result is None
        assert cache_key not in client._cache  # Should be cleaned up

    def test_cache_result_cache_disabled(self):
        """Test _cache_result with cache disabled."""
        config = SDKConfig(cache_enabled=False)
        client = DevHubClient(config)

        client._cache_result("test", ContextRequest(), {"data": "test"})

        assert len(client._cache) == 0

    def test_cache_result_cache_enabled(self):
        """Test _cache_result with cache enabled."""
        config = SDKConfig(cache_enabled=True)
        client = DevHubClient(config)

        request = ContextRequest()
        test_data = {"data": "test"}

        client._cache_result("test", request, test_data)

        cache_key = f"test_{hash(str(request))}"
        assert cache_key in client._cache
        timestamp, cached_data = client._cache[cache_key]
        assert cached_data == test_data
        assert timestamp <= time.time()

    @pytest.mark.asyncio
    async def test_build_bundle_context_full_flow(self):
        """Test _build_bundle_context with full successful flow."""
        client = DevHubClient()
        client._devhub_config = DevHubConfig()

        mock_repo = Repository(owner="test", name="repo")
        request = ContextRequest(
            jira_key="TEST-123",
            pr_number=456,
            include_jira=True,
            include_pr=True,
            include_diff=True,
            include_comments=True,
        )

        with patch("devhub.sdk.get_repository_info") as mock_get_repo, \
             patch("devhub.sdk.get_current_branch") as mock_get_branch, \
             patch("devhub.sdk._gather_bundle_data") as mock_gather:

            mock_get_repo.return_value = Success(mock_repo)
            mock_get_branch.return_value = Success("main")
            mock_gather.return_value = Success('{"test": "data"}')

            result = await client._build_bundle_context(request)

            assert isinstance(result, Success)

    @pytest.mark.asyncio
    async def test_build_bundle_context_gather_failure(self):
        """Test _build_bundle_context with gather data failure."""
        client = DevHubClient()
        client._devhub_config = DevHubConfig()

        mock_repo = Repository(owner="test", name="repo")
        request = ContextRequest()

        with patch("devhub.sdk.get_repository_info") as mock_get_repo, \
             patch("devhub.sdk.get_current_branch") as mock_get_branch, \
             patch("devhub.sdk._gather_bundle_data") as mock_gather:

            mock_get_repo.return_value = Success(mock_repo)
            mock_get_branch.return_value = Success("main")
            mock_gather.return_value = Failure("Gather failed")

            result = await client._build_bundle_context(request)

            assert isinstance(result, Failure)
            assert result.failure() == "Gather failed"

    @pytest.mark.asyncio
    async def test_ensure_initialized_already_initialized(self):
        """Test _ensure_initialized when already initialized."""
        client = DevHubClient()
        client._devhub_config = DevHubConfig()

        result = await client._ensure_initialized()

        assert isinstance(result, Success)

    @pytest.mark.asyncio
    async def test_get_jira_issue_not_initialized(self):
        """Test get_jira_issue when not initialized."""
        client = DevHubClient()

        with patch.object(client, "initialize") as mock_init:
            mock_init.return_value = Failure("Init failed")

            result = await client.get_jira_issue("TEST-123")

            assert isinstance(result, Failure)
            assert result.failure() == "Init failed"

    @pytest.mark.asyncio
    async def test_get_jira_issue_with_fallback_credentials(self):
        """Test get_jira_issue with fallback to environment credentials."""
        client = DevHubClient()
        client._devhub_config = DevHubConfig()

        mock_jira_issue = JiraIssue(
            key="TEST-123",
            summary="Test issue",
            description="Test description",
            raw_data={}
        )

        with patch("devhub.sdk.get_jira_credentials_from_config") as mock_get_config_creds, \
             patch("devhub.sdk.get_jira_credentials") as mock_get_env_creds, \
             patch("devhub.sdk.fetch_jira_issue") as mock_fetch:

            mock_get_config_creds.return_value = None
            mock_get_env_creds.return_value = ("user", "token", "https://test.atlassian.net")
            mock_fetch.return_value = Success(mock_jira_issue)

            result = await client.get_jira_issue("TEST-123")

            assert isinstance(result, Success)
            assert result.unwrap() == mock_jira_issue

    @pytest.mark.asyncio
    async def test_get_pr_details_exception(self):
        """Test get_pr_details with exception."""
        client = DevHubClient()

        with patch("devhub.sdk.get_repository_info") as mock_get_repo:
            mock_get_repo.side_effect = ValueError("Test error")

            result = await client.get_pr_details(123)

            assert isinstance(result, Failure)
            assert "Failed to get PR details: Test error" in result.failure()

    @pytest.mark.asyncio
    async def test_get_pr_comments_exception(self):
        """Test get_pr_comments with exception."""
        client = DevHubClient()

        with patch("devhub.sdk.get_repository_info") as mock_get_repo:
            mock_get_repo.side_effect = TypeError("Test error")

            result = await client.get_pr_comments(123)

            assert isinstance(result, Failure)
            assert "Failed to get PR comments: Test error" in result.failure()

    @pytest.mark.asyncio
    async def test_execute_cli_command_no_capture(self):
        """Test execute_cli_command without output capture."""
        client = DevHubClient()

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (None, None)

        with patch("asyncio.create_subprocess_exec") as mock_create_process, \
             patch("asyncio.wait_for") as mock_wait:
            mock_create_process.return_value = mock_process
            mock_wait.return_value = (None, None)

            result = await client.execute_cli_command(["test"], capture_output=False)

            assert isinstance(result, Success)
            assert result.unwrap() == ""

    @pytest.mark.asyncio
    async def test_execute_cli_command_os_error(self):
        """Test execute_cli_command with OSError."""
        client = DevHubClient()

        with patch("asyncio.create_subprocess_exec") as mock_create_process:
            mock_create_process.side_effect = OSError("Process error")

            result = await client.execute_cli_command(["test"])

            assert isinstance(result, Failure)
            assert "CLI command error: Process error" in result.failure()

    @pytest.mark.asyncio
    async def test_stream_pr_updates_exception_handling(self):
        """Test stream_pr_updates with exception handling in loop."""
        client = DevHubClient()

        call_count = 0

        async def mock_get_pr_details(pr_number):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call succeeds and returns update
                return Success({"number": pr_number, "updated_at": "2023-01-01T00:00:00Z"})
            else:
                # Subsequent calls fail to test error handling
                raise ValueError("Stream error")

        with patch.object(client, "get_pr_details", mock_get_pr_details), \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:

            updates = []
            stream = client.stream_pr_updates(123)

            # Get first update
            update = await stream.__anext__()
            updates.append(update)

            # Close the stream to prevent hanging
            await stream.aclose()

            assert len(updates) == 1
            assert updates[0].update_type == "pr_updated"

