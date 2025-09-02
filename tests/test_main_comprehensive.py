"""Comprehensive tests for DevHub main.py module CLI functionality."""

import argparse
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch

from returns.result import Failure
from returns.result import Success

from devhub.config import DevHubConfig
from devhub.config import JiraConfig
from devhub.config import OrganizationConfig
from devhub.main import BundleConfig
from devhub.main import BundleData
from devhub.main import JiraCredentials
from devhub.main import JiraIssue
from devhub.main import OutputPaths
from devhub.main import Repository
from devhub.main import ReviewComment
from devhub.main import _create_jira_issue
from devhub.main import _gather_bundle_data
from devhub.main import _parse_comments_response
from devhub.main import _parse_pr_number_from_output
from devhub.main import _parse_repo_json
from devhub.main import _parse_search_results
from devhub.main import assert_git_repo
from devhub.main import check_command_exists
from devhub.main import create_output_paths
from devhub.main import create_parser
from devhub.main import ensure_directory
from devhub.main import extract_jira_key_from_branch
from devhub.main import fetch_jira_issue
from devhub.main import fetch_pr_details
from devhub.main import fetch_pr_diff
from devhub.main import find_pr_by_branch
from devhub.main import find_pr_by_jira_key
from devhub.main import format_json_output
from devhub.main import get_current_branch
from devhub.main import get_jira_credentials
from devhub.main import get_jira_credentials_from_config
from devhub.main import get_repository_info
from devhub.main import handle_bundle_command
from devhub.main import handle_doctor_command
from devhub.main import main
from devhub.main import now_slug
from devhub.main import resolve_jira_key_with_config
from devhub.main import resolve_pr_number
from devhub.main import run_command
from devhub.main import write_json_file
from devhub.main import write_text_file


class TestMainCLIFunctions:
    """Test main CLI utility functions."""

    def test_check_command_exists_success(self):
        """Test command existence check success."""
        with patch("devhub.main.run_command") as mock_run:
            # Create a proper subprocess.CompletedProcess mock
            mock_process = Mock()
            mock_process.stdout = "/usr/bin/git"
            mock_run.return_value = Success(mock_process)

            result = check_command_exists("git")

            assert isinstance(result, Success)
            assert result.unwrap() == "/usr/bin/git"

    def test_check_command_exists_failure(self):
        """Test command existence check failure."""
        with patch("devhub.main.run_command") as mock_run:
            mock_run.return_value = Failure("Command not found")

            result = check_command_exists("nonexistent")

            assert isinstance(result, Failure)

    def test_check_command_exists_empty_path(self):
        """Test command existence check with empty path."""
        with patch("devhub.main.run_command") as mock_run:
            mock_process = Mock()
            mock_process.stdout = ""
            mock_run.return_value = Success(mock_process)

            result = check_command_exists("git")

            assert isinstance(result, Failure)
            assert "Command not found" in result.failure()

    def test_run_command_success(self):
        """Test successful command execution."""
        with patch("subprocess.run") as mock_run:
            mock_process = Mock()
            mock_process.returncode = 0
            mock_process.stdout = "output"
            mock_process.stderr = ""
            mock_run.return_value = mock_process

            result = run_command(["echo", "test"])

            assert isinstance(result, Success)
            # The result should be the actual process object
            assert result.unwrap().stdout == "output"

    def test_run_command_failure(self):
        """Test command execution failure."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, ["false"])

            result = run_command(["false"])

            assert isinstance(result, Failure)

    def test_run_command_timeout(self):
        """Test command execution timeout."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(["sleep"], 30)

            result = run_command(["sleep", "100"])

            assert isinstance(result, Failure)
            assert "timed out" in result.failure().lower()

    def test_run_command_process_error(self):
        """Test command execution with process error."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, ["cmd"])

            result = run_command(["false"])

            assert isinstance(result, Failure)

    def test_format_json_output_default(self):
        """Test JSON formatting with default format."""
        data = {"test": "value", "number": 42}
        result = format_json_output(data, "json")

        assert json.loads(result) == data
        assert "\n" in result  # Should be pretty-printed

    def test_format_json_output_compact(self):
        """Test JSON formatting with compact format."""
        data = {"test": "value", "number": 42}
        result = format_json_output(data, "compact")

        assert json.loads(result) == data
        assert "\n" not in result  # Should be compact

    def test_format_json_output_jsonlines(self):
        """Test JSON formatting with jsonlines format."""
        data = {"test": "value", "number": 42}
        result = format_json_output(data, "jsonlines")

        assert json.loads(result) == data
        assert "\n" not in result  # Should be single line

    def test_now_slug_format(self):
        """Test timestamp slug format."""
        result = now_slug()

        # Should match YYYYMMDD-HHMMSS format
        assert len(result) == 15
        assert result[8] == "-"

    def test_extract_jira_key_from_branch_valid(self):
        """Test extracting Jira key from valid branch name."""
        branches = [
            ("feature/ABC-123-some-feature", "ABC-123"),
            ("bugfix/XYZ-456", "XYZ-456"),
            ("hotfix/PROJECT-789-urgent-fix", "PROJECT-789"),
            ("ABC-123", "ABC-123"),
        ]

        for branch, expected in branches:
            result = extract_jira_key_from_branch(branch)
            assert result == expected

    def test_extract_jira_key_from_branch_invalid(self):
        """Test extracting Jira key from invalid branch name."""
        branches = [
            "main",
            "feature/some-feature",
            "bugfix/fix-123",  # lowercase project
            "abc-123",  # lowercase project
            "",
        ]

        for branch in branches:
            result = extract_jira_key_from_branch(branch)
            assert result is None

    def test_create_output_paths_with_explicit_dir(self):
        """Test creating output paths with explicit directory."""
        result = create_output_paths("/custom/path", None, None)

        assert result.base_dir == Path("/custom/path")

    def test_create_output_paths_with_jira_key(self):
        """Test creating output paths with Jira key."""
        with patch("devhub.main.now_slug", return_value="20240101-120000"):
            result = create_output_paths(None, "TEST-123", None)

            expected_path = Path("review-bundles/TEST-123-20240101-120000")
            assert result.base_dir == expected_path

    def test_create_output_paths_with_pr_number(self):
        """Test creating output paths with PR number."""
        with patch("devhub.main.now_slug", return_value="20240101-120000"):
            result = create_output_paths(None, None, 456)

            expected_path = Path("review-bundles/pr-456-20240101-120000")
            assert result.base_dir == expected_path

    def test_create_output_paths_default(self):
        """Test creating output paths with defaults."""
        with patch("devhub.main.now_slug", return_value="20240101-120000"):
            result = create_output_paths(None, None, None)

            expected_path = Path("review-bundles/bundle-20240101-120000")
            assert result.base_dir == expected_path

    def test_ensure_directory_success(self):
        """Test successful directory creation."""
        with patch("pathlib.Path.mkdir") as mock_mkdir:
            mock_mkdir.return_value = None

            result = ensure_directory(Path("/test/path"))

            assert isinstance(result, Success)
            mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    def test_ensure_directory_failure(self):
        """Test directory creation failure."""
        with patch("pathlib.Path.mkdir") as mock_mkdir:
            mock_mkdir.side_effect = OSError("Permission denied")

            result = ensure_directory(Path("/test/path"))

            assert isinstance(result, Failure)
            assert "Permission denied" in result.failure()

    def test_write_text_file_success(self):
        """Test successful text file writing."""
        with patch("pathlib.Path.write_text") as mock_write:
            mock_write.return_value = None

            result = write_text_file(Path("/test/file.txt"), "content")

            assert isinstance(result, Success)
            mock_write.assert_called_once_with("content", encoding="utf-8")

    def test_write_text_file_failure(self):
        """Test text file writing failure."""
        with patch("pathlib.Path.write_text") as mock_write:
            mock_write.side_effect = OSError("Disk full")

            result = write_text_file(Path("/test/file.txt"), "content")

            assert isinstance(result, Failure)
            assert "Disk full" in result.failure()

    def test_write_json_file_success(self):
        """Test successful JSON file writing."""
        data = {"test": "value"}

        with patch("devhub.main.write_text_file") as mock_write:
            mock_write.return_value = Success(None)

            result = write_json_file(Path("/test/file.json"), data)

            assert isinstance(result, Success)
            mock_write.assert_called_once()
            args = mock_write.call_args[0]
            assert json.loads(args[1]) == data

    def test_write_json_file_serialization_error(self):
        """Test JSON file writing with serialization error."""
        # Create an object that can't be JSON serialized
        data = {"test": object()}

        result = write_json_file(Path("/test/file.json"), data)

        assert isinstance(result, Failure)
        assert "Failed to serialize JSON" in result.failure()

    def test_assert_git_repo_success(self):
        """Test successful git repository check."""
        with patch("devhub.main.run_command") as mock_run:
            mock_process = Mock()
            mock_process.stdout = "true"
            mock_run.return_value = Success(mock_process)

            result = assert_git_repo()

            assert isinstance(result, Success)

    def test_assert_git_repo_failure(self):
        """Test git repository check failure."""
        with patch("devhub.main.run_command") as mock_run:
            mock_run.return_value = Failure("Not a git repository")

            result = assert_git_repo()

            assert isinstance(result, Failure)

    def test_parse_repo_json_success(self):
        """Test successful repository JSON parsing."""
        json_data = {"owner": {"login": "testowner"}, "name": "testrepo"}

        result = _parse_repo_json(json.dumps(json_data))

        assert isinstance(result, Success)
        repo = result.unwrap()
        assert repo.owner == "testowner"
        assert repo.name == "testrepo"

    def test_parse_repo_json_missing_owner(self):
        """Test repository JSON parsing with missing owner."""
        json_data = {"name": "testrepo"}

        result = _parse_repo_json(json.dumps(json_data))

        assert isinstance(result, Failure)
        assert "missing owner or name" in result.failure()

    def test_parse_repo_json_invalid_json(self):
        """Test repository JSON parsing with invalid JSON."""
        result = _parse_repo_json("invalid json")

        assert isinstance(result, Failure)
        assert "Failed to parse repository JSON" in result.failure()

    def test_get_repository_info_success(self):
        """Test successful repository info retrieval."""
        repo_data = {"owner": {"login": "testowner"}, "name": "testrepo"}

        with patch("devhub.main.check_command_exists") as mock_check, patch("devhub.main.run_command") as mock_run:
            mock_check.return_value = Success("/usr/bin/gh")
            mock_process = Mock()
            mock_process.stdout = json.dumps(repo_data)
            mock_run.return_value = Success(mock_process)

            result = get_repository_info()

            assert isinstance(result, Success)
            repo = result.unwrap()
            assert repo.owner == "testowner"
            assert repo.name == "testrepo"

    def test_get_repository_info_gh_not_found(self):
        """Test repository info retrieval when gh is not found."""
        with patch("devhub.main.check_command_exists") as mock_check:
            mock_check.return_value = Failure("gh not found")

            result = get_repository_info()

            assert isinstance(result, Failure)

    def test_get_current_branch_success(self):
        """Test successful current branch retrieval."""
        with patch("devhub.main.run_command") as mock_run:
            mock_process = Mock()
            mock_process.stdout = "feature-branch"
            mock_run.return_value = Success(mock_process)

            result = get_current_branch()

            assert isinstance(result, Success)
            assert result.unwrap() == "feature-branch"

    def test_get_current_branch_failure(self):
        """Test current branch retrieval failure."""
        with patch("devhub.main.run_command") as mock_run:
            mock_run.return_value = Failure("Not a git repository")

            result = get_current_branch()

            assert isinstance(result, Failure)

    def test_get_current_branch_empty(self):
        """Test current branch retrieval with empty output."""
        with patch("devhub.main.run_command") as mock_run:
            mock_process = Mock()
            mock_process.stdout = ""
            mock_run.return_value = Success(mock_process)

            result = get_current_branch()

            assert isinstance(result, Failure)
            assert "Could not determine current branch" in result.failure()

    def test_parse_pr_number_from_output_simple_number(self):
        """Test parsing PR number from simple number output."""
        with patch("devhub.main.run_command") as mock_run:
            mock_process = Mock()
            mock_process.stdout = "123"
            mock_run.return_value = Success(mock_process)

            result = _parse_pr_number_from_output(mock_process)

            assert isinstance(result, Success)
            assert result.unwrap() == 123

    def test_parse_pr_number_from_output_empty(self):
        """Test parsing PR number from empty output."""
        with patch("devhub.main.run_command") as mock_run:
            mock_process = Mock()
            mock_process.stdout = ""
            mock_run.return_value = Success(mock_process)

            result = _parse_pr_number_from_output(mock_process)

            assert isinstance(result, Success)
            assert result.unwrap() is None

    def test_parse_pr_number_from_output_json_search(self):
        """Test parsing PR number from JSON search results."""
        search_data = {"items": [{"number": 456, "title": "Test PR"}]}

        mock_process = Mock()
        mock_process.stdout = json.dumps(search_data)

        result = _parse_pr_number_from_output(mock_process)

        assert isinstance(result, Success)
        assert result.unwrap() == 456

    def test_parse_pr_number_from_output_json_no_items(self):
        """Test parsing PR number from JSON with no items."""
        search_data = {"items": []}

        mock_process = Mock()
        mock_process.stdout = json.dumps(search_data)

        result = _parse_pr_number_from_output(mock_process)

        assert isinstance(result, Success)
        assert result.unwrap() is None

    def test_parse_pr_number_from_output_json_no_number(self):
        """Test parsing PR number from JSON with missing number."""
        search_data = {
            "items": [
                {"title": "Test PR"}  # Missing number field
            ]
        }

        mock_process = Mock()
        mock_process.stdout = json.dumps(search_data)

        result = _parse_pr_number_from_output(mock_process)

        assert isinstance(result, Failure)
        assert "No PR number found in search results" in result.failure()

    def test_parse_pr_number_from_output_invalid_number(self):
        """Test parsing PR number from invalid number string."""
        mock_process = Mock()
        mock_process.stdout = "not-a-number"

        result = _parse_pr_number_from_output(mock_process)

        assert isinstance(result, Success)
        assert result.unwrap() is None

    def test_parse_pr_number_from_output_list_response(self):
        """Test parsing PR number from list response."""
        mock_process = Mock()
        mock_process.stdout = json.dumps([])  # Empty list

        result = _parse_pr_number_from_output(mock_process)

        assert isinstance(result, Success)
        assert result.unwrap() is None

    def test_find_pr_by_branch_success(self):
        """Test successful PR finding by branch."""
        repo = Repository(owner="testowner", name="testrepo")

        with patch("devhub.main.run_command") as mock_run:
            mock_process = Mock()
            mock_process.stdout = "123"
            mock_run.return_value = Success(mock_process)

            result = find_pr_by_branch(repo, "feature-branch")

            assert isinstance(result, Success)
            assert result.unwrap() == 123

    def test_find_pr_by_jira_key_success(self):
        """Test successful PR finding by Jira key."""
        repo = Repository(owner="testowner", name="testrepo")
        search_data = {"items": [{"number": 789, "title": "TEST-123: Fix issue"}]}

        with patch("devhub.main.run_command") as mock_run:
            mock_process = Mock()
            mock_process.stdout = json.dumps(search_data)
            mock_run.return_value = Success(mock_process)

            result = find_pr_by_jira_key(repo, "TEST-123")

            assert isinstance(result, Success)
            assert result.unwrap() == 789

    def test_parse_search_results_success(self):
        """Test successful search results parsing."""
        search_data = {"items": [{"number": 123, "title": "Test PR"}]}

        result = _parse_search_results(json.dumps(search_data))

        assert isinstance(result, Success)
        assert result.unwrap() == 123

    def test_parse_search_results_no_items(self):
        """Test search results parsing with no items."""
        search_data = {"items": []}

        result = _parse_search_results(json.dumps(search_data))

        assert isinstance(result, Success)
        assert result.unwrap() is None

    def test_parse_search_results_invalid_json(self):
        """Test search results parsing with invalid JSON."""
        result = _parse_search_results("invalid json")

        assert isinstance(result, Failure)
        assert "Failed to parse search JSON" in result.failure()

    def test_fetch_pr_details_success(self):
        """Test successful PR details fetching."""
        repo = Repository(owner="testowner", name="testrepo")
        pr_data = {"number": 123, "title": "Test PR", "body": "Test description"}

        with patch("devhub.main.run_command") as mock_run:
            mock_process = Mock()
            mock_process.stdout = json.dumps(pr_data)
            mock_run.return_value = Success(mock_process)

            result = fetch_pr_details(repo, 123)

            assert isinstance(result, Success)
            assert result.unwrap() == pr_data

    def test_fetch_pr_diff_success(self):
        """Test successful PR diff fetching."""
        diff_content = "--- a/file.py\n+++ b/file.py\n@@ -1,3 +1,3 @@"

        with patch("devhub.main.run_command") as mock_run:
            mock_process = Mock()
            mock_process.stdout = diff_content
            mock_run.return_value = Success(mock_process)

            result = fetch_pr_diff(123)

            assert isinstance(result, Success)
            assert result.unwrap() == diff_content

    def test_get_jira_credentials_success(self):
        """Test successful Jira credentials retrieval from environment."""
        env_vars = {
            "JIRA_BASE_URL": "https://test.atlassian.net",
            "JIRA_EMAIL": "test@example.com",
            "JIRA_API_TOKEN": "test-token",
        }

        with patch.dict(os.environ, env_vars):
            result = get_jira_credentials()

            assert result is not None
            assert result.base_url == "https://test.atlassian.net"
            assert result.email == "test@example.com"
            assert result.api_token == "test-token"

    def test_get_jira_credentials_missing_vars(self):
        """Test Jira credentials retrieval with missing environment variables."""
        with patch.dict(os.environ, {}, clear=True):
            result = get_jira_credentials()

            assert result is None

    def test_get_jira_credentials_from_config_success(self):
        """Test getting Jira credentials from config."""
        jira_config = JiraConfig(
            base_url="https://config.atlassian.net", email="config@example.com", api_token="config-token"
        )
        org_config = OrganizationConfig(name="test-org", jira=jira_config)
        config = DevHubConfig(organizations=(org_config,))

        result = get_jira_credentials_from_config(config, "test-org")

        assert result is not None
        assert isinstance(result, JiraCredentials)
        assert result.base_url == "https://config.atlassian.net"
        assert result.email == "config@example.com"
        assert result.api_token == "config-token"

    def test_get_jira_credentials_from_config_no_org(self):
        """Test getting Jira credentials from config with missing organization."""
        config = DevHubConfig()

        result = get_jira_credentials_from_config(config, "nonexistent-org")

        assert result is None

    def test_get_jira_credentials_from_config_incomplete_config(self):
        """Test getting Jira credentials from config with incomplete Jira config."""
        jira_config = JiraConfig(base_url="https://test.atlassian.net")  # Missing email and token
        org_config = OrganizationConfig(name="test-org", jira=jira_config)
        config = DevHubConfig(organizations=(org_config,))

        result = get_jira_credentials_from_config(config, "test-org")

        assert result is None

    def test_resolve_jira_key_with_config_explicit_key(self):
        """Test resolving Jira key with explicit key provided."""
        config = DevHubConfig()

        result = resolve_jira_key_with_config(config, branch="main", org_name=None, explicit_key="EXPLICIT-123")

        assert result == "EXPLICIT-123"

    def test_resolve_jira_key_with_config_from_branch(self):
        """Test resolving Jira key from branch name."""
        jira_config = JiraConfig(
            base_url="https://test.atlassian.net", email="test@example.com", api_token="test-token"
        )
        org_config = OrganizationConfig(name="test-org", jira=jira_config)
        config = DevHubConfig(default_organization="test-org", organizations=(org_config,))

        result = resolve_jira_key_with_config(config, branch="feature/TEST-456-implement-feature")

        assert result == "TEST-456"

    def test_resolve_jira_key_with_config_from_project_prefix(self):
        """Test resolving Jira key using default project prefix."""
        jira_config = JiraConfig(
            base_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test-token",
            default_project_prefix="PROJECT",
        )
        org_config = OrganizationConfig(name="test-org", jira=jira_config)
        config = DevHubConfig(default_organization="test-org", organizations=(org_config,))

        result = resolve_jira_key_with_config(config, branch="feature-789-some-feature")

        assert result == "PROJECT-789"

    def test_resolve_jira_key_with_config_no_match(self):
        """Test resolving Jira key with no match found."""
        config = DevHubConfig()

        result = resolve_jira_key_with_config(config, branch="main")

        assert result is None

    def test_fetch_jira_issue_success_curl(self):
        """Test successful Jira issue fetching using curl."""
        credentials = JiraCredentials(
            base_url="https://test.atlassian.net", email="test@example.com", api_token="test-token"
        )

        mock_response_data = {"key": "TEST-123", "fields": {"summary": "Test issue", "description": "Test description"}}

        with patch("devhub.main.run_command") as mock_run:
            mock_process = Mock()
            mock_process.stdout = json.dumps(mock_response_data)
            mock_run.return_value = Success(mock_process)

            result = fetch_jira_issue(credentials, "TEST-123")

            assert isinstance(result, Success)
            issue = result.unwrap()
            assert issue.key == "TEST-123"
            assert issue.summary == "Test issue"
            assert issue.description == "Test description"

    def test_fetch_jira_issue_curl_fallback_to_urllib(self):
        """Test Jira issue fetching falling back from curl to urllib."""
        credentials = JiraCredentials(
            base_url="https://test.atlassian.net", email="test@example.com", api_token="test-token"
        )

        mock_response_data = {"key": "TEST-123", "fields": {"summary": "Test issue", "description": "Test description"}}

        with patch("devhub.main.run_command") as mock_run, patch("urllib.request.urlopen") as mock_urlopen:
            # Make curl fail
            mock_run.return_value = Failure("curl not found")

            # Mock urllib response
            mock_response = Mock()
            mock_response.read.return_value = json.dumps(mock_response_data).encode()
            mock_urlopen.return_value.__enter__.return_value = mock_response

            result = fetch_jira_issue(credentials, "TEST-123")

            assert isinstance(result, Success)
            issue = result.unwrap()
            assert issue.key == "TEST-123"

    def test_fetch_jira_issue_http_error(self):
        """Test Jira issue fetching with HTTP error."""
        import urllib.error

        credentials = JiraCredentials(
            base_url="https://test.atlassian.net", email="test@example.com", api_token="test-token"
        )

        with patch("devhub.main.run_command") as mock_run, patch("urllib.request.urlopen") as mock_urlopen:
            # Make curl fail
            mock_run.return_value = Failure("curl failed")

            # Mock HTTP error
            error = urllib.error.HTTPError(
                url="https://test.atlassian.net/rest/api/3/issue/TEST-123", code=404, msg="Not Found", hdrs={}, fp=None
            )
            error.read = Mock(return_value=b"Issue not found")
            mock_urlopen.side_effect = error

            result = fetch_jira_issue(credentials, "TEST-123")

            assert isinstance(result, Failure)
            assert "HTTP error 404" in result.failure()

    def test_fetch_jira_issue_invalid_curl_response(self):
        """Test Jira issue fetching with invalid curl response falling back to urllib."""
        credentials = JiraCredentials(
            base_url="https://test.atlassian.net", email="test@example.com", api_token="test-token"
        )

        mock_response_data = {"key": "TEST-123", "fields": {"summary": "Test issue", "description": "Test description"}}

        with patch("devhub.main.run_command") as mock_run, patch("urllib.request.urlopen") as mock_urlopen:
            # Make curl return invalid response (no fields)
            mock_process = Mock()
            mock_process.stdout = json.dumps({"key": "TEST-123"})  # Missing fields
            mock_run.return_value = Success(mock_process)

            # Mock urllib response
            mock_response = Mock()
            mock_response.read.return_value = json.dumps(mock_response_data).encode()
            mock_urlopen.return_value.__enter__.return_value = mock_response

            result = fetch_jira_issue(credentials, "TEST-123")

            assert isinstance(result, Success)
            issue = result.unwrap()
            assert issue.key == "TEST-123"

    def test_create_jira_issue_complex_description(self):
        """Test creating Jira issue with complex description object."""
        raw_data = {
            "key": "TEST-123",
            "fields": {
                "summary": "Test issue",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Complex description"}]}],
                },
            },
        }

        result = _create_jira_issue("TEST-123", raw_data)

        assert result.key == "TEST-123"
        assert result.summary == "Test issue"
        assert isinstance(result.description, str)
        assert "type" in result.description

    def test_parse_comments_response_graphql_format(self):
        """Test parsing comments response in GraphQL format."""
        graphql_response = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {
                                    "isResolved": False,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "id": "comment1",
                                                "body": "Test comment",
                                                "path": "test.py",
                                                "createdAt": "2024-01-01T12:00:00Z",
                                                "author": {"login": "testuser"},
                                                "diffHunk": "@@ -1,3 +1,3 @@",
                                            }
                                        ]
                                    },
                                }
                            ]
                        }
                    }
                }
            }
        }

        result = _parse_comments_response(json.dumps(graphql_response), 10)

        assert isinstance(result, Success)
        comments = result.unwrap()
        assert len(comments) == 1
        assert comments[0].id == "comment1"
        assert comments[0].body == "Test comment"
        assert comments[0].author == "testuser"

    def test_parse_comments_response_list_format(self):
        """Test parsing comments response in simple list format."""
        list_response = [
            {
                "id": "comment1",
                "body": "Test comment",
                "path": "test.py",
                "user": {"login": "testuser"},
                "created_at": "2024-01-01T12:00:00Z",
                "diff_hunk": "@@ -1,3 +1,3 @@",
            }
        ]

        result = _parse_comments_response(json.dumps(list_response), 10)

        assert isinstance(result, Success)
        comments = result.unwrap()
        assert len(comments) == 1
        assert comments[0].id == "comment1"
        assert comments[0].body == "Test comment"

    def test_parse_comments_response_invalid_json(self):
        """Test parsing comments response with invalid JSON."""
        result = _parse_comments_response("invalid json", 10)

        assert isinstance(result, Failure)
        assert "Failed to parse comments response" in result.failure()

    def test_resolve_pr_number_explicit_provided(self):
        """Test resolving PR number when explicit number is provided."""
        repo = Repository(owner="test", name="repo")

        result = resolve_pr_number(repo, 123, "branch", "JIRA-456")

        assert isinstance(result, Success)
        assert result.unwrap() == 123

    def test_resolve_pr_number_from_branch(self):
        """Test resolving PR number from branch name."""
        repo = Repository(owner="test", name="repo")

        with patch("devhub.main.find_pr_by_branch") as mock_find:
            mock_find.return_value = Success(456)

            result = resolve_pr_number(repo, None, "feature-branch", None)

            assert isinstance(result, Success)
            assert result.unwrap() == 456

    def test_resolve_pr_number_from_jira_key(self):
        """Test resolving PR number from Jira key."""
        repo = Repository(owner="test", name="repo")

        with (
            patch("devhub.main.find_pr_by_branch") as mock_find_branch,
            patch("devhub.main.find_pr_by_jira_key") as mock_find_jira,
        ):
            mock_find_branch.return_value = Success(None)
            mock_find_jira.return_value = Success(789)

            result = resolve_pr_number(repo, None, "branch", "JIRA-123")

            assert isinstance(result, Success)
            assert result.unwrap() == 789

    def test_resolve_pr_number_jira_not_found(self):
        """Test resolving PR number when Jira key doesn't match any PR."""
        repo = Repository(owner="test", name="repo")

        with (
            patch("devhub.main.find_pr_by_branch") as mock_find_branch,
            patch("devhub.main.find_pr_by_jira_key") as mock_find_jira,
        ):
            mock_find_branch.return_value = Success(None)
            mock_find_jira.return_value = Success(None)

            result = resolve_pr_number(repo, None, "branch", "JIRA-123")

            assert isinstance(result, Failure)
            assert "No PR found for Jira key: JIRA-123" in result.failure()

    def test_resolve_pr_number_no_identifiers(self):
        """Test resolving PR number with no identifiers."""
        repo = Repository(owner="test", name="repo")

        result = resolve_pr_number(repo, None, None, None)

        assert isinstance(result, Success)
        assert result.unwrap() is None


class TestBundleData:
    """Test BundleData class functionality."""

    def test_bundle_data_to_dict_full_content(self):
        """Test BundleData to_dict with full content."""
        jira_issue = JiraIssue(
            key="TEST-123", summary="Test issue", description="Test description", raw_data={"key": "TEST-123"}
        )

        pr_data = {"number": 456, "title": "Test PR"}
        comments = (
            ReviewComment(
                id="comment1",
                body="Test comment",
                path="test.py",
                author="testuser",
                created_at="2024-01-01T12:00:00Z",
                diff_hunk="@@ -1,3 +1,3 @@",
                resolved=False,
            ),
        )

        repo = Repository(owner="testowner", name="testrepo")

        bundle = BundleData(
            jira_issue=jira_issue,
            pr_data=pr_data,
            pr_diff="diff content",
            comments=comments,
            repository=repo,
            branch="main",
            metadata={"test": "value"},
        )

        result = bundle.to_dict(include_content=True)

        assert "jira" in result
        assert result["jira"]["key"] == "TEST-123"
        assert "pull_request" in result
        assert result["pull_request"]["number"] == 456
        assert "diff" in result
        assert result["diff"] == "diff content"
        assert "comments" in result
        assert len(result["comments"]) == 1
        assert result["metadata"]["repository"]["owner"] == "testowner"
        assert result["metadata"]["branch"] == "main"

    def test_bundle_data_to_dict_metadata_only(self):
        """Test BundleData to_dict with metadata only."""
        repo = Repository(owner="testowner", name="testrepo")
        bundle = BundleData(repository=repo, branch="main")

        result = bundle.to_dict(include_content=False)

        assert "jira" not in result
        assert "pull_request" not in result
        assert "diff" not in result
        assert "comments" not in result
        assert "metadata" in result
        assert result["metadata"]["repository"]["owner"] == "testowner"


class TestCLI:
    """Test CLI argument parsing and command handling."""

    def test_create_parser(self):
        """Test parser creation."""
        parser = create_parser()

        assert parser is not None
        # Don't check prog name as it varies between direct execution and pytest
        assert hasattr(parser, "parse_args")

    def test_main_bundle_command_success(self):
        """Test main function with successful bundle command."""
        with patch("devhub.main.handle_bundle_command") as mock_handle:
            mock_handle.return_value = Success("Bundle created successfully")

            result = main(["bundle", "--jira-key", "TEST-123"])

            assert result == 0
            mock_handle.assert_called_once()

    def test_main_bundle_command_failure(self):
        """Test main function with failed bundle command."""
        with patch("devhub.main.handle_bundle_command") as mock_handle, patch("sys.stderr") as mock_stderr:
            mock_handle.return_value = Failure("Bundle creation failed")

            result = main(["bundle", "--jira-key", "TEST-123"])

            assert result == 1
            mock_stderr.write.assert_called_once()

    def test_main_doctor_command_success(self):
        """Test main function with successful doctor command."""
        with patch("devhub.main.handle_doctor_command") as mock_handle:
            mock_handle.return_value = Success("All checks passed")

            result = main(["doctor"])

            assert result == 0
            mock_handle.assert_called_once()

    def test_main_doctor_command_failure(self):
        """Test main function with failed doctor command."""
        with patch("devhub.main.handle_doctor_command") as mock_handle, patch("sys.stderr") as mock_stderr:
            mock_handle.return_value = Failure("Doctor checks failed")

            result = main(["doctor"])

            assert result == 1
            mock_stderr.write.assert_called_once()

    def test_main_help_argument(self):
        """Test main function with help argument."""
        result = main(["--help"])

        assert result == 0

    def test_main_version_argument(self):
        """Test main function with version argument."""
        result = main(["--version"])

        assert result == 0

    def test_main_invalid_command(self):
        """Test main function with invalid command."""
        result = main(["invalid-command"])

        assert result == 2

    def test_main_no_command(self):
        """Test main function with no command."""
        result = main([])

        assert result == 2

    def test_handle_doctor_command_all_checks_pass(self):
        """Test doctor command with all checks passing."""
        with (
            patch("devhub.main.run_command") as mock_run,
            patch("devhub.main.check_command_exists") as mock_check,
            patch("devhub.main.assert_git_repo") as mock_git,
            patch("devhub.main.get_jira_credentials") as mock_creds,
        ):
            mock_run.return_value = Success(Mock())
            mock_check.return_value = Success("/usr/bin/gh")
            mock_git.return_value = Success(None)
            mock_creds.return_value = JiraCredentials("url", "email", "token")

            result = handle_doctor_command()

            assert isinstance(result, Success)
            output = result.unwrap()
            assert "✓ git is available" in output
            assert "✓ GitHub CLI (gh) is available" in output
            assert "✓ Current directory is a git repository" in output
            assert "✓ Jira credentials are configured" in output

    def test_handle_doctor_command_some_checks_fail(self):
        """Test doctor command with some checks failing."""
        with (
            patch("devhub.main.run_command") as mock_run,
            patch("devhub.main.check_command_exists") as mock_check,
            patch("devhub.main.assert_git_repo") as mock_git,
            patch("devhub.main.get_jira_credentials") as mock_creds,
        ):
            mock_run.return_value = Failure("git not found")
            mock_check.return_value = Failure("gh not found")
            mock_git.return_value = Failure("not a git repo")
            mock_creds.return_value = None

            result = handle_doctor_command()

            assert isinstance(result, Success)
            output = result.unwrap()
            assert "✗ git is not available" in output
            assert "✗ GitHub CLI (gh) is not available" in output
            assert "✗ Current directory is not a git repository" in output
            assert "⚠ Jira credentials not found" in output

    def test_handle_bundle_command_full_flow(self):
        """Test bundle command with full successful flow."""
        args = argparse.Namespace(
            jira_key="TEST-123",
            pr_number=456,
            branch="main",
            output_dir="/custom/output",
            limit=10,
            organization="testorg",
            no_jira=False,
            no_pr=False,
            no_diff=False,
            no_comments=False,
            config=None,
        )

        bundle_data = {
            "metadata": {"repository": {"owner": "testowner", "name": "testrepo"}, "branch": "main"},
            "jira": {"key": "TEST-123", "summary": "Test issue"},
            "pull_request": {"number": 456, "title": "Test PR"},
        }

        with (
            patch("devhub.main.load_config_with_environment") as mock_config,
            patch("devhub.main.assert_git_repo") as mock_git,
            patch("devhub.main.get_repository_info") as mock_repo,
            patch("devhub.main._gather_bundle_data") as mock_gather,
            patch("devhub.main.ensure_directory") as mock_ensure,
            patch("devhub.main.write_json_file") as mock_write,
        ):
            mock_config.return_value = Success(DevHubConfig())
            mock_git.return_value = Success(None)
            mock_repo.return_value = Success(Repository("testowner", "testrepo"))
            mock_gather.return_value = Success(json.dumps(bundle_data))
            mock_ensure.return_value = Success(None)
            mock_write.return_value = Success(None)

            result = handle_bundle_command(args)

            assert isinstance(result, Success)
            assert "Bundle saved to:" in result.unwrap()

    def test_handle_bundle_command_git_repo_failure(self):
        """Test bundle command when not in git repository."""
        args = argparse.Namespace(config=None)

        with (
            patch("devhub.main.load_config_with_environment") as mock_config,
            patch("devhub.main.assert_git_repo") as mock_git,
        ):
            mock_config.return_value = Success(DevHubConfig())
            mock_git.return_value = Failure("Not a git repository")

            result = handle_bundle_command(args)

            assert isinstance(result, Failure)
            assert "Not a git repository" in result.failure()

    def test_handle_bundle_command_with_branch_resolution(self):
        """Test bundle command with automatic branch resolution."""
        args = argparse.Namespace(
            jira_key=None,
            pr_number=None,
            branch=None,
            output_dir=None,
            limit=10,
            organization=None,
            no_jira=False,
            no_pr=False,
            no_diff=False,
            no_comments=False,
            config=None,
        )

        with (
            patch("devhub.main.load_config_with_environment") as mock_config,
            patch("devhub.main.assert_git_repo") as mock_git,
            patch("devhub.main.get_repository_info") as mock_repo,
            patch("devhub.main.get_current_branch") as mock_branch,
            patch("devhub.main.resolve_jira_key_with_config") as mock_jira,
            patch("devhub.main.resolve_pr_number") as mock_pr,
            patch("devhub.main._gather_bundle_data") as mock_gather,
            patch("devhub.main.ensure_directory") as mock_ensure,
            patch("devhub.main.write_json_file") as mock_write,
        ):
            mock_config.return_value = Success(DevHubConfig())
            mock_git.return_value = Success(None)
            mock_repo.return_value = Success(Repository("testowner", "testrepo"))
            mock_branch.return_value = Success("feature/TEST-123-new-feature")
            mock_jira.return_value = "TEST-123"
            mock_pr.return_value = Success(456)
            mock_gather.return_value = Success('{"metadata": {}}')
            mock_ensure.return_value = Success(None)
            mock_write.return_value = Success(None)

            result = handle_bundle_command(args)

            assert isinstance(result, Success)

    def test_handle_bundle_command_invalid_json(self):
        """Test bundle command with invalid JSON from gather."""
        args = argparse.Namespace(jira_key="TEST-123", config=None)

        with (
            patch("devhub.main.load_config_with_environment") as mock_config,
            patch("devhub.main.assert_git_repo") as mock_git,
            patch("devhub.main.get_repository_info") as mock_repo,
            patch("devhub.main.resolve_pr_number") as mock_pr,
            patch("devhub.main._gather_bundle_data") as mock_gather,
        ):
            mock_config.return_value = Success(DevHubConfig())
            mock_git.return_value = Success(None)
            mock_repo.return_value = Success(Repository("testowner", "testrepo"))
            mock_pr.return_value = Success(None)
            mock_gather.return_value = Success("invalid json")

            result = handle_bundle_command(args)

            assert isinstance(result, Failure)
            assert "Invalid bundle JSON" in result.failure()


class TestGatherBundleData:
    """Test _gather_bundle_data function."""

    def test_gather_bundle_data_full_success(self):
        """Test gathering bundle data with all components successful."""
        args = argparse.Namespace(metadata_only=False, format="json")
        config = BundleConfig(include_jira=True, include_pr=True, include_diff=True, include_comments=True, limit=10)
        repo = Repository("testowner", "testrepo")
        devhub_config = DevHubConfig()

        jira_issue = JiraIssue("TEST-123", "Test issue", "Description", {})
        pr_data = {"number": 456, "title": "Test PR"}

        with (
            patch("devhub.main.get_jira_credentials_from_config") as mock_creds_config,
            patch("devhub.main.get_jira_credentials") as mock_creds,
            patch("devhub.main.collect_jira_data") as mock_jira,
            patch("devhub.main.collect_pr_data") as mock_pr,
            patch("devhub.main.collect_pr_diff") as mock_diff,
            patch("devhub.main.collect_unresolved_comments") as mock_comments,
        ):
            mock_creds_config.return_value = None
            mock_creds.return_value = JiraCredentials("url", "email", "token")
            mock_jira.return_value = Success(jira_issue)
            mock_pr.return_value = Success(pr_data)
            mock_diff.return_value = Success("diff content")
            mock_comments.return_value = Success(())

            result = _gather_bundle_data(args, config, repo, "main", "TEST-123", 456, devhub_config)

            assert isinstance(result, Success)
            bundle_json = result.unwrap()
            bundle_data = json.loads(bundle_json)

            assert "jira" in bundle_data
            assert "pull_request" in bundle_data
            assert "diff" in bundle_data

    def test_gather_bundle_data_metadata_only(self):
        """Test gathering bundle data with metadata only."""
        args = argparse.Namespace(metadata_only=True, format="json")
        config = BundleConfig()
        repo = Repository("testowner", "testrepo")
        devhub_config = DevHubConfig()

        result = _gather_bundle_data(args, config, repo, "main", None, None, devhub_config)

        assert isinstance(result, Success)
        bundle_json = result.unwrap()
        bundle_data = json.loads(bundle_json)

        assert "jira" not in bundle_data
        assert "pull_request" not in bundle_data
        assert "metadata" in bundle_data

    def test_gather_bundle_data_jira_failure(self):
        """Test gathering bundle data with Jira fetch failure."""
        args = argparse.Namespace(metadata_only=False, format="json")
        config = BundleConfig(include_jira=True)
        repo = Repository("testowner", "testrepo")
        devhub_config = DevHubConfig()

        with (
            patch("devhub.main.get_jira_credentials") as mock_creds,
            patch("devhub.main.collect_jira_data") as mock_jira,
        ):
            mock_creds.return_value = JiraCredentials("url", "email", "token")
            mock_jira.return_value = Failure("Jira API error")

            result = _gather_bundle_data(args, config, repo, "main", "TEST-123", None, devhub_config)

            assert isinstance(result, Failure)
            assert "Failed to fetch Jira data" in result.failure()

    def test_gather_bundle_data_pr_failure(self):
        """Test gathering bundle data with PR fetch failure."""
        args = argparse.Namespace(metadata_only=False, format="json")
        config = BundleConfig(include_pr=True)
        repo = Repository("testowner", "testrepo")
        devhub_config = DevHubConfig()

        with patch("devhub.main.collect_pr_data") as mock_pr:
            mock_pr.return_value = Failure("PR API error")

            result = _gather_bundle_data(args, config, repo, "main", None, 456, devhub_config)

            assert isinstance(result, Failure)
            assert "Failed to fetch PR data" in result.failure()

    def test_gather_bundle_data_compact_format(self):
        """Test gathering bundle data with compact format."""
        args = argparse.Namespace(metadata_only=False, format="compact")
        config = BundleConfig()
        repo = Repository("testowner", "testrepo")
        devhub_config = DevHubConfig()

        result = _gather_bundle_data(args, config, repo, "main", None, None, devhub_config)

        assert isinstance(result, Success)
        bundle_json = result.unwrap()

        # Compact format should not have indentation
        assert "\n" not in bundle_json


class TestOutputPaths:
    """Test OutputPaths class functionality."""

    def test_output_paths_methods(self):
        """Test all OutputPaths methods."""
        paths = OutputPaths(base_dir=Path("/test"))

        assert paths.jira_json("TEST-123") == Path("/test/jira_TEST-123.json")
        assert paths.jira_md("TEST-123") == Path("/test/jira_TEST-123.md")
        assert paths.pr_json(456) == Path("/test/pr_456.json")
        assert paths.pr_md(456) == Path("/test/pr_456.md")
        assert paths.pr_diff(456) == Path("/test/pr_456.diff")
        assert paths.comments_json(456) == Path("/test/unresolved_comments_pr456.json")


class TestAdditionalCoverage:
    """Additional tests to cover missing lines and edge cases."""

    def test_get_current_branch_empty(self):
        """Test current branch retrieval with empty output."""
        with patch("devhub.main.run_command") as mock_run:
            mock_process = Mock()
            mock_process.stdout = ""
            mock_run.return_value = Success(mock_process)

            result = get_current_branch()

            assert isinstance(result, Failure)
            assert "Could not determine current branch" in result.failure()

    def test_parse_pr_number_from_output_list_response(self):
        """Test parsing PR number from list response."""
        mock_process = Mock()
        mock_process.stdout = json.dumps([])  # Empty list

        result = _parse_pr_number_from_output(mock_process)

        assert isinstance(result, Success)
        assert result.unwrap() is None

    def test_resolve_pr_number_branch_failure(self):
        """Test resolving PR number when branch search fails."""
        repo = Repository(owner="test", name="repo")

        with patch("devhub.main.find_pr_by_branch") as mock_find:
            mock_find.return_value = Failure("Branch search failed")

            result = resolve_pr_number(repo, None, "feature-branch", None)

            assert isinstance(result, Failure)
            assert "Branch search failed" in result.failure()

    def test_resolve_pr_number_jira_search_failure(self):
        """Test resolving PR number when Jira search fails."""
        repo = Repository(owner="test", name="repo")

        with (
            patch("devhub.main.find_pr_by_branch") as mock_find_branch,
            patch("devhub.main.find_pr_by_jira_key") as mock_find_jira,
        ):
            mock_find_branch.return_value = Success(None)
            mock_find_jira.return_value = Failure("Jira search failed")

            result = resolve_pr_number(repo, None, "branch", "JIRA-123")

            assert isinstance(result, Failure)
            assert "Jira search failed" in result.failure()

    def test_fetch_jira_issue_json_decode_error_curl(self):
        """Test Jira issue fetching with JSON decode error from curl."""
        credentials = JiraCredentials(
            base_url="https://test.atlassian.net", email="test@example.com", api_token="test-token"
        )

        mock_response_data = {"key": "TEST-123", "fields": {"summary": "Test issue", "description": "Test description"}}

        with patch("devhub.main.run_command") as mock_run, patch("urllib.request.urlopen") as mock_urlopen:
            # Make curl return invalid JSON
            mock_process = Mock()
            mock_process.stdout = "invalid json"
            mock_run.return_value = Success(mock_process)

            # Mock urllib response
            mock_response = Mock()
            mock_response.read.return_value = json.dumps(mock_response_data).encode()
            mock_urlopen.return_value.__enter__.return_value = mock_response

            result = fetch_jira_issue(credentials, "TEST-123")

            assert isinstance(result, Success)
            issue = result.unwrap()
            assert issue.key == "TEST-123"

    def test_fetch_jira_issue_url_error(self):
        """Test Jira issue fetching with URL error."""
        import urllib.error

        credentials = JiraCredentials(
            base_url="https://test.atlassian.net", email="test@example.com", api_token="test-token"
        )

        with patch("devhub.main.run_command") as mock_run, patch("urllib.request.urlopen") as mock_urlopen:
            # Make curl fail
            mock_run.return_value = Failure("curl failed")

            # Mock URL error
            mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

            result = fetch_jira_issue(credentials, "TEST-123")

            assert isinstance(result, Failure)
            assert "Request failed" in result.failure()

    def test_fetch_jira_issue_json_decode_error_urllib(self):
        """Test Jira issue fetching with JSON decode error from urllib."""
        credentials = JiraCredentials(
            base_url="https://test.atlassian.net", email="test@example.com", api_token="test-token"
        )

        with patch("devhub.main.run_command") as mock_run, patch("urllib.request.urlopen") as mock_urlopen:
            # Make curl fail
            mock_run.return_value = Failure("curl failed")

            # Mock urllib response with invalid JSON
            mock_response = Mock()
            mock_response.read.return_value = b"invalid json"
            mock_urlopen.return_value.__enter__.return_value = mock_response

            result = fetch_jira_issue(credentials, "TEST-123")

            assert isinstance(result, Failure)
            assert "Request failed" in result.failure()

    def test_parse_comments_response_missing_author(self):
        """Test parsing comments response with missing author."""
        graphql_response = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {
                                    "isResolved": False,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "id": "comment1",
                                                "body": "Test comment",
                                                "path": "test.py",
                                                "createdAt": "2024-01-01T12:00:00Z",
                                                "author": None,  # Missing author
                                                "diffHunk": "@@ -1,3 +1,3 @@",
                                            }
                                        ]
                                    },
                                }
                            ]
                        }
                    }
                }
            }
        }

        result = _parse_comments_response(json.dumps(graphql_response), 10)

        assert isinstance(result, Success)
        comments = result.unwrap()
        assert len(comments) == 1
        assert comments[0].author is None

    def test_gather_bundle_data_no_jira_credentials(self):
        """Test gathering bundle data when no Jira credentials available."""
        args = argparse.Namespace(metadata_only=False, format="json")
        config = BundleConfig(include_jira=True)
        repo = Repository("testowner", "testrepo")
        devhub_config = DevHubConfig()

        with (
            patch("devhub.main.get_jira_credentials_from_config") as mock_creds_config,
            patch("devhub.main.get_jira_credentials") as mock_creds,
        ):
            mock_creds_config.return_value = None
            mock_creds.return_value = None

            result = _gather_bundle_data(args, config, repo, "main", "TEST-123", None, devhub_config)

            assert isinstance(result, Success)
            bundle_json = result.unwrap()
            bundle_data = json.loads(bundle_json)

            # Should succeed but without Jira data
            assert "jira" not in bundle_data

    def test_gather_bundle_data_diff_failure(self):
        """Test gathering bundle data with diff fetch failure."""
        args = argparse.Namespace(metadata_only=False, format="json")
        config = BundleConfig(include_pr=True, include_diff=True)
        repo = Repository("testowner", "testrepo")
        devhub_config = DevHubConfig()

        with patch("devhub.main.collect_pr_data") as mock_pr, patch("devhub.main.collect_pr_diff") as mock_diff:
            mock_pr.return_value = Success({"number": 456, "title": "Test PR"})
            mock_diff.return_value = Failure("Diff fetch failed")

            result = _gather_bundle_data(args, config, repo, "main", None, 456, devhub_config)

            assert isinstance(result, Failure)
            assert "Failed to fetch PR diff" in result.failure()

    def test_gather_bundle_data_comments_failure(self):
        """Test gathering bundle data with comments fetch failure."""
        args = argparse.Namespace(metadata_only=False, format="json")
        config = BundleConfig(include_pr=True, include_comments=True)
        repo = Repository("testowner", "testrepo")
        devhub_config = DevHubConfig()

        with (
            patch("devhub.main.collect_pr_data") as mock_pr,
            patch("devhub.main.collect_pr_diff") as mock_diff,
            patch("devhub.main.collect_unresolved_comments") as mock_comments,
        ):
            mock_pr.return_value = Success({"number": 456, "title": "Test PR"})
            mock_diff.return_value = Success("diff content")
            mock_comments.return_value = Failure("Comments fetch failed")

            result = _gather_bundle_data(args, config, repo, "main", None, 456, devhub_config)

            assert isinstance(result, Failure)
            assert "Failed to fetch comments" in result.failure()

    def test_main_argument_parse_error(self):
        """Test main function with argument parsing error."""
        # Test with invalid arguments that would cause argparse to fail
        result = main(["bundle", "--invalid-arg"])

        assert result == 2

    def test_main_system_exit_handling(self):
        """Test main function handling SystemExit from argparse."""
        with patch("devhub.main.create_parser") as mock_parser:
            parser_mock = Mock()
            parser_mock.parse_args.side_effect = SystemExit(1)
            mock_parser.return_value = parser_mock

            result = main(["--help"])

            assert result == 1

    def test_main_system_exit_none_code(self):
        """Test main function handling SystemExit with None code."""
        with patch("devhub.main.create_parser") as mock_parser:
            parser_mock = Mock()
            parser_mock.parse_args.side_effect = SystemExit(None)
            mock_parser.return_value = parser_mock

            result = main(["--help"])

            assert result == 0

    def test_main_invalid_namespace(self):
        """Test main function with invalid namespace (no command)."""
        with patch("devhub.main.create_parser") as mock_parser:
            parser_mock = Mock()
            # Return namespace without command attribute
            args_mock = Mock(spec=[])  # No command attribute
            parser_mock.parse_args.return_value = args_mock
            mock_parser.return_value = parser_mock

            result = main([])

            assert result == 2

    def test_handle_bundle_command_config_failure(self):
        """Test bundle command with config loading failure."""
        args = argparse.Namespace(config=None)

        with (
            patch("devhub.main.load_config_with_environment") as mock_config,
            patch("devhub.main.assert_git_repo") as mock_git,
            patch("devhub.main.get_repository_info") as mock_repo,
            patch("devhub.main.resolve_pr_number") as mock_pr,
            patch("devhub.main._gather_bundle_data") as mock_gather,
            patch("devhub.main.ensure_directory") as mock_ensure,
            patch("devhub.main.write_json_file") as mock_write,
        ):
            # Config fails but should fallback to default
            mock_config.return_value = Failure("Config load failed")
            mock_git.return_value = Success(None)
            mock_repo.return_value = Success(Repository("testowner", "testrepo"))
            mock_pr.return_value = Success(None)
            mock_gather.return_value = Success('{"metadata": {}}')
            mock_ensure.return_value = Success(None)
            mock_write.return_value = Success(None)

            result = handle_bundle_command(args)

            assert isinstance(result, Success)

    def test_handle_bundle_command_repo_info_failure(self):
        """Test bundle command with repository info failure."""
        args = argparse.Namespace(config=None)

        with (
            patch("devhub.main.load_config_with_environment") as mock_config,
            patch("devhub.main.assert_git_repo") as mock_git,
            patch("devhub.main.get_repository_info") as mock_repo,
        ):
            mock_config.return_value = Success(DevHubConfig())
            mock_git.return_value = Success(None)
            mock_repo.return_value = Failure("Repository info failed")

            result = handle_bundle_command(args)

            assert isinstance(result, Failure)
            assert "Repository info failed" in result.failure()

    def test_handle_bundle_command_pr_resolution_failure(self):
        """Test bundle command with PR resolution failure."""
        args = argparse.Namespace(
            jira_key=None,
            pr_number=None,
            branch=None,
            output_dir=None,
            limit=10,
            organization=None,
            no_jira=False,
            no_pr=False,
            no_diff=False,
            no_comments=False,
            config=None,
        )

        with (
            patch("devhub.main.load_config_with_environment") as mock_config,
            patch("devhub.main.assert_git_repo") as mock_git,
            patch("devhub.main.get_repository_info") as mock_repo,
            patch("devhub.main.resolve_pr_number") as mock_pr,
        ):
            mock_config.return_value = Success(DevHubConfig())
            mock_git.return_value = Success(None)
            mock_repo.return_value = Success(Repository("testowner", "testrepo"))
            mock_pr.return_value = Failure("PR resolution failed")

            result = handle_bundle_command(args)

            assert isinstance(result, Failure)
            assert "PR resolution failed" in result.failure()

    def test_handle_bundle_command_gather_failure(self):
        """Test bundle command with data gathering failure."""
        args = argparse.Namespace(jira_key="TEST-123", config=None)

        with (
            patch("devhub.main.load_config_with_environment") as mock_config,
            patch("devhub.main.assert_git_repo") as mock_git,
            patch("devhub.main.get_repository_info") as mock_repo,
            patch("devhub.main.resolve_pr_number") as mock_pr,
            patch("devhub.main._gather_bundle_data") as mock_gather,
        ):
            mock_config.return_value = Success(DevHubConfig())
            mock_git.return_value = Success(None)
            mock_repo.return_value = Success(Repository("testowner", "testrepo"))
            mock_pr.return_value = Success(None)
            mock_gather.return_value = Failure("Data gathering failed")

            result = handle_bundle_command(args)

            assert isinstance(result, Failure)
            assert "Data gathering failed" in result.failure()

    def test_handle_bundle_command_ensure_directory_failure(self):
        """Test bundle command with directory creation failure."""
        args = argparse.Namespace(jira_key="TEST-123", config=None)

        with (
            patch("devhub.main.load_config_with_environment") as mock_config,
            patch("devhub.main.assert_git_repo") as mock_git,
            patch("devhub.main.get_repository_info") as mock_repo,
            patch("devhub.main.resolve_pr_number") as mock_pr,
            patch("devhub.main._gather_bundle_data") as mock_gather,
            patch("devhub.main.ensure_directory") as mock_ensure,
        ):
            mock_config.return_value = Success(DevHubConfig())
            mock_git.return_value = Success(None)
            mock_repo.return_value = Success(Repository("testowner", "testrepo"))
            mock_pr.return_value = Success(None)
            mock_gather.return_value = Success('{"metadata": {}}')
            mock_ensure.return_value = Failure("Directory creation failed")

            result = handle_bundle_command(args)

            assert isinstance(result, Failure)
            assert "Directory creation failed" in result.failure()

    def test_handle_bundle_command_write_json_failure(self):
        """Test bundle command with JSON writing failure."""
        args = argparse.Namespace(jira_key="TEST-123", config=None)

        with (
            patch("devhub.main.load_config_with_environment") as mock_config,
            patch("devhub.main.assert_git_repo") as mock_git,
            patch("devhub.main.get_repository_info") as mock_repo,
            patch("devhub.main.resolve_pr_number") as mock_pr,
            patch("devhub.main._gather_bundle_data") as mock_gather,
            patch("devhub.main.ensure_directory") as mock_ensure,
            patch("devhub.main.write_json_file") as mock_write,
        ):
            mock_config.return_value = Success(DevHubConfig())
            mock_git.return_value = Success(None)
            mock_repo.return_value = Success(Repository("testowner", "testrepo"))
            mock_pr.return_value = Success(None)
            mock_gather.return_value = Success('{"metadata": {}}')
            mock_ensure.return_value = Success(None)
            mock_write.return_value = Failure("JSON write failed")

            result = handle_bundle_command(args)

            assert isinstance(result, Failure)
            assert "JSON write failed" in result.failure()

    def test_bundle_data_to_dict_no_repository(self):
        """Test BundleData to_dict with no repository."""
        bundle = BundleData()

        result = bundle.to_dict(include_content=True)

        assert result["metadata"]["repository"] is None
        assert result["metadata"]["branch"] is None

    def test_create_output_paths_with_pathlike(self):
        """Test creating output paths with PathLike object."""
        from pathlib import PurePath

        result = create_output_paths(PurePath("/custom/path"), None, None)

        assert result.base_dir == Path("/custom/path")

    def test_resolve_jira_key_no_branch(self):
        """Test resolving Jira key with no branch provided."""
        config = DevHubConfig()

        result = resolve_jira_key_with_config(config, branch=None)

        assert result is None

    def test_resolve_jira_key_no_issue_match(self):
        """Test resolving Jira key with no issue number match in branch."""
        jira_config = JiraConfig(
            base_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test-token",
            default_project_prefix="PROJECT",
        )
        org_config = OrganizationConfig(name="test-org", jira=jira_config)
        config = DevHubConfig(default_organization="test-org", organizations=(org_config,))

        result = resolve_jira_key_with_config(config, branch="feature/some-feature")

        assert result is None

    def test_parse_comments_response_empty_nodes(self):
        """Test parsing comments response with empty nodes."""
        graphql_response = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {
                                    "isResolved": False,
                                    "comments": {
                                        "nodes": []  # Empty nodes
                                    },
                                }
                            ]
                        }
                    }
                }
            }
        }

        result = _parse_comments_response(json.dumps(graphql_response), 10)

        assert isinstance(result, Success)
        comments = result.unwrap()
        assert len(comments) == 0

    def test_parse_comments_response_sorting(self):
        """Test parsing comments response with sorting by created_at."""
        graphql_response = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {
                                    "isResolved": False,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "id": "comment1",
                                                "body": "First comment",
                                                "createdAt": "2024-01-01T12:00:00Z",
                                                "author": {"login": "user1"},
                                            }
                                        ]
                                    },
                                },
                                {
                                    "isResolved": False,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "id": "comment2",
                                                "body": "Second comment",
                                                "createdAt": "2024-01-02T12:00:00Z",
                                                "author": {"login": "user2"},
                                            }
                                        ]
                                    },
                                },
                            ]
                        }
                    }
                }
            }
        }

        result = _parse_comments_response(json.dumps(graphql_response), 10)

        assert isinstance(result, Success)
        comments = result.unwrap()
        assert len(comments) == 2
        # Should be sorted by created_at desc (most recent first)
        assert comments[0].id == "comment2"
        assert comments[1].id == "comment1"

    def test_parse_comments_response_limit(self):
        """Test parsing comments response with limit."""
        list_response = [{"id": f"comment{i}", "body": f"Comment {i}"} for i in range(20)]

        result = _parse_comments_response(json.dumps(list_response), 5)

        assert isinstance(result, Success)
        comments = result.unwrap()
        assert len(comments) == 5
