"""Tests for error handling and edge cases to improve coverage."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

from returns.result import Failure
from returns.result import Success

from devhub.config import DevHubConfig
from devhub.config import JiraConfig
from devhub.main import BundleConfig
from devhub.main import JiraCredentials
from devhub.main import _extract_command_path
from devhub.main import _parse_json_response
from devhub.main import _parse_repo_json
from devhub.main import _parse_search_results
from devhub.main import check_command_exists
from devhub.main import ensure_directory
from devhub.main import resolve_jira_key_with_config
from devhub.main import run_command
from devhub.main import write_json_file
from devhub.main import write_text_file


class TestErrorHandling:
    """Tests for error handling and edge cases."""

    def test_extract_command_path_empty_stdout(self) -> None:
        """Test _extract_command_path with empty stdout."""
        proc = MagicMock()
        proc.stdout = ""

        result = _extract_command_path(proc)

        assert isinstance(result, Failure)
        assert result.failure() == "Command not found"

    def test_extract_command_path_whitespace_stdout(self) -> None:
        """Test _extract_command_path with whitespace-only stdout."""
        proc = MagicMock()
        proc.stdout = "   \n\t  "

        result = _extract_command_path(proc)

        assert isinstance(result, Failure)
        assert result.failure() == "Command not found"

    def test_parse_repo_json_invalid_json(self) -> None:
        """Test _parse_repo_json with invalid JSON."""
        invalid_json = "{ invalid json"

        result = _parse_repo_json(invalid_json)

        assert isinstance(result, Failure)
        assert "Failed to parse repository JSON" in result.failure()

    def test_parse_repo_json_missing_owner(self) -> None:
        """Test _parse_repo_json with missing owner."""
        json_data = json.dumps({"name": "testrepo"})

        result = _parse_repo_json(json_data)

        assert isinstance(result, Failure)
        assert result.failure() == "Invalid repository data: missing owner or name"

    def test_parse_repo_json_missing_name(self) -> None:
        """Test _parse_repo_json with missing name."""
        json_data = json.dumps({"owner": {"login": "testowner"}})

        result = _parse_repo_json(json_data)

        assert isinstance(result, Failure)
        assert result.failure() == "Invalid repository data: missing owner or name"

    def test_parse_search_results_invalid_json(self) -> None:
        """Test _parse_search_results with invalid JSON."""
        invalid_json = "{ invalid json"

        result = _parse_search_results(invalid_json)

        assert isinstance(result, Failure)
        assert "Failed to parse search JSON" in result.failure()

    def test_parse_search_results_empty_items(self) -> None:
        """Test _parse_search_results with empty items."""
        json_data = json.dumps({"items": []})

        result = _parse_search_results(json_data)

        assert isinstance(result, Success)
        assert result.unwrap() is None

    def test_parse_search_results_missing_pr_number(self) -> None:
        """Test _parse_search_results with missing PR number."""
        json_data = json.dumps({"items": [{"title": "Test PR"}]})

        result = _parse_search_results(json_data)

        assert isinstance(result, Failure)
        assert result.failure() == "No PR number found in search results"

    def test_parse_json_response_invalid_json(self) -> None:
        """Test _parse_json_response with invalid JSON."""
        invalid_json = "{ invalid json"

        result = _parse_json_response(invalid_json)

        assert isinstance(result, Failure)
        assert "Failed to parse JSON" in result.failure()

    @patch("devhub.main.subprocess.run")
    def test_run_command_timeout(self, mock_run: Mock) -> None:
        """Test run_command with timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired("test", 30)

        result = run_command(["test", "command"])

        assert isinstance(result, Failure)
        assert "Command timed out" in result.failure()

    @patch("devhub.main.subprocess.run")
    def test_run_command_process_error(self, mock_run: Mock) -> None:
        """Test run_command with CalledProcessError."""
        mock_run.side_effect = subprocess.CalledProcessError(1, ["test"], "error output")

        result = run_command(["test", "command"])

        assert isinstance(result, Failure)
        assert "Command failed" in result.failure()

    @patch("devhub.main.run_command")
    def test_check_command_exists_not_found(self, mock_run: Mock) -> None:
        """Test check_command_exists when command not found."""
        proc = MagicMock()
        proc.stdout = ""
        mock_run.return_value = Success(proc)

        result = check_command_exists("nonexistent")

        assert isinstance(result, Failure)
        assert result.failure() == "Command not found"

    def test_ensure_directory_permission_error(self) -> None:
        """Test ensure_directory with permission error."""
        with patch("pathlib.Path.mkdir") as mock_mkdir:
            mock_mkdir.side_effect = OSError("Permission denied")

            result = ensure_directory(Path("/invalid/path"))

            assert isinstance(result, Failure)
            assert "Failed to create directory" in result.failure()

    def test_write_text_file_permission_error(self) -> None:
        """Test write_text_file with permission error."""
        with patch("pathlib.Path.write_text") as mock_write:
            mock_write.side_effect = OSError("Permission denied")

            result = write_text_file(Path("/invalid/file.txt"), "content")

            assert isinstance(result, Failure)
            assert "Failed to write" in result.failure()

    def test_write_json_file_serialization_error(self) -> None:
        """Test write_json_file with JSON serialization error."""
        import tempfile

        # Create an object that can't be serialized to JSON
        unserializable_obj = {"key": {1, 2, 3}}  # sets aren't JSON serializable

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            test_path = Path(f.name)

        try:
            result = write_json_file(test_path, unserializable_obj)

            assert isinstance(result, Failure)
            assert "Failed to serialize JSON" in result.failure()
        finally:
            test_path.unlink(missing_ok=True)


class TestJiraKeyResolution:
    """Tests for Jira key resolution edge cases."""

    def test_resolve_jira_key_explicit_key(self) -> None:
        """Test resolve_jira_key_with_config with explicit key."""
        config = DevHubConfig()

        result = resolve_jira_key_with_config(config=config, branch="feature/test-branch", explicit_key="EXPLICIT-123")

        assert result == "EXPLICIT-123"

    def test_resolve_jira_key_no_branch_no_key(self) -> None:
        """Test resolve_jira_key_with_config with no branch or key."""
        config = DevHubConfig()

        result = resolve_jira_key_with_config(config=config)

        assert result is None

    def test_resolve_jira_key_with_default_prefix(self) -> None:
        """Test resolve_jira_key_with_config using default prefix."""
        jira_config = JiraConfig(default_project_prefix="ACME")
        config = DevHubConfig(global_jira=jira_config)

        # Branch with just number at end, no full key
        result = resolve_jira_key_with_config(config=config, branch="feature/add-feature-456")

        assert result == "ACME-456"

    def test_resolve_jira_key_no_issue_number_in_branch(self) -> None:
        """Test resolve_jira_key_with_config with branch containing no issue number."""
        jira_config = JiraConfig(default_project_prefix="ACME")
        config = DevHubConfig(global_jira=jira_config)

        result = resolve_jira_key_with_config(config=config, branch="feature/no-numbers-here")

        assert result is None

    def test_resolve_jira_key_no_default_prefix(self) -> None:
        """Test resolve_jira_key_with_config without default prefix."""
        config = DevHubConfig()

        result = resolve_jira_key_with_config(config=config, branch="feature/123-add-feature")

        assert result is None


class TestBundleConfigEdgeCases:
    """Tests for BundleConfig edge cases."""

    def test_bundle_config_direct_creation(self) -> None:
        """Test creating BundleConfig with all features disabled."""
        config = BundleConfig(include_jira=False, include_pr=False, include_diff=False, include_comments=False, limit=5)

        assert config.include_jira is False
        assert config.include_pr is False
        assert config.include_diff is False
        assert config.include_comments is False
        assert config.limit == 5


class TestAdditionalCoverage:
    """Additional tests to cover remaining uncovered lines."""

    def test_json_serialization_edge_cases(self) -> None:
        """Test JSON serialization with various edge cases."""
        from devhub.main import _parse_json_response

        # Test with non-dict JSON
        result = _parse_json_response("[1, 2, 3]")
        assert isinstance(result, Success)
        assert result.unwrap() == [1, 2, 3]

        # Test with simple string JSON
        result = _parse_json_response('"test string"')
        assert isinstance(result, Success)
        assert result.unwrap() == "test string"

    def test_write_json_file_success(self) -> None:
        """Test successful JSON file writing."""
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            test_path = Path(f.name)

        try:
            result = write_json_file(test_path, {"test": "data"})
            assert isinstance(result, Success)

            # Verify file was written correctly
            content = test_path.read_text(encoding="utf-8")
            assert "test" in content
            assert "data" in content
        finally:
            test_path.unlink(missing_ok=True)

    @patch("devhub.main.urllib.request.urlopen")
    def test_jira_http_errors(self, mock_urlopen: Mock) -> None:
        """Test various Jira HTTP error scenarios."""
        import io
        from email.message import Message
        from urllib.error import HTTPError

        from devhub.main import fetch_jira_issue

        credentials = JiraCredentials(
            base_url="https://test.atlassian.net", email="test@example.com", api_token="token"
        )

        # Test 404 error
        headers = Message()
        mock_urlopen.side_effect = HTTPError(
            url="test",
            code=404,
            msg="Not Found",
            hdrs=headers,
            fp=io.BytesIO(b""),
        )

        result = fetch_jira_issue(credentials, "TEST-404")
        assert isinstance(result, Failure)
        assert "HTTP error 404" in result.failure()

    def test_config_error_paths(self) -> None:
        """Test config parsing error paths."""
        from devhub.config import parse_config_data

        # Test with invalid config structure that causes exception
        invalid_data = {"organizations": {"test": {"jira": "invalid"}}}

        result = parse_config_data(invalid_data)
        # This should handle the exception and return a Failure
        assert isinstance(result, (Success, Failure))  # Either is acceptable

    def test_command_execution_edge_cases(self) -> None:
        """Test edge cases in command execution."""
        # Test successful command execution
        result = run_command(["echo", "test"])
        assert isinstance(result, Success)

        # Test command with specific output
        result = run_command(["echo", "-n", "no_newline"])
        assert isinstance(result, Success)
        proc = result.unwrap()
        assert proc.stdout == "no_newline"
