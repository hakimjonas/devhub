"""Comprehensive tests for DevHub main.py module CLI functionality."""

import argparse
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, mock_open

import pytest
from returns.result import Failure, Success

from devhub.config import DevHubConfig, JiraConfig, OrganizationConfig
from devhub.main import (
    BundleConfig,
    JiraCredentials,
    JiraIssue,
    Repository,
    ReviewComment,
    check_command_exists,
    ensure_directory,
    fetch_jira_issue,
    fetch_pr_details,
    fetch_pr_diff,
    fetch_unresolved_comments,
    get_current_branch,
    get_jira_credentials,
    get_jira_credentials_from_config,
    get_repository_info,
    handle_bundle_command,
    main,
    resolve_jira_key_with_config,
    resolve_pr_number,
    run_command,
    write_json_file,
    write_text_file,
    _gather_bundle_data,
)


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


class TestFileOperations:
    """Test file operation functions."""

    def test_ensure_directory_success(self):
        """Test successful directory creation."""
        with patch("pathlib.Path.mkdir") as mock_mkdir:
            result = ensure_directory(Path("/test/dir"))

            assert isinstance(result, Success)
            mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    def test_ensure_directory_permission_error(self):
        """Test directory creation with permission error."""
        with patch("pathlib.Path.mkdir") as mock_mkdir:
            mock_mkdir.side_effect = PermissionError("Permission denied")

            result = ensure_directory(Path("/test/dir"))

            assert isinstance(result, Failure)
            assert "Permission denied" in result.failure()

    def test_write_text_file_success(self):
        """Test successful text file writing."""
        with patch("pathlib.Path.write_text") as mock_write:
            result = write_text_file(Path("/test/file.txt"), "content")

            assert isinstance(result, Success)
            mock_write.assert_called_once_with("content", encoding="utf-8")

    def test_write_text_file_error(self):
        """Test text file writing with error."""
        with patch("pathlib.Path.write_text") as mock_write:
            mock_write.side_effect = OSError("Write error")

            result = write_text_file(Path("/test/file.txt"), "content")

            assert isinstance(result, Failure)
            assert "Write error" in result.failure()

    def test_write_json_file_success(self):
        """Test successful JSON file writing."""
        with patch("pathlib.Path.write_text") as mock_write:
            data = {"key": "value", "number": 123}
            result = write_json_file(Path("/test/file.json"), data)

            assert isinstance(result, Success)
            # Verify JSON was written
            mock_write.assert_called_once()
            written_content = mock_write.call_args[0][0]
            assert "key" in written_content
            assert "value" in written_content

    def test_write_json_file_serialization_error(self):
        """Test JSON file writing with serialization error."""
        with patch("pathlib.Path.write_text") as mock_write:
            # Create object that can't be serialized
            class UnserializableClass:
                pass

            data = {"obj": UnserializableClass()}
            result = write_json_file(Path("/test/file.json"), data)

            assert isinstance(result, Failure)
            assert "serialize" in result.failure().lower()


class TestJiraFunctions:
    """Test Jira-related functions."""

    def test_get_jira_credentials_from_environment(self):
        """Test getting Jira credentials from environment variables."""
        with patch.dict(os.environ, {
            "JIRA_BASE_URL": "https://test.atlassian.net",
            "JIRA_EMAIL": "test@example.com",
            "JIRA_API_TOKEN": "test-token"
        }):
            result = get_jira_credentials()

            assert result is not None
            assert isinstance(result, JiraCredentials)
            assert result.base_url == "https://test.atlassian.net"
            assert result.email == "test@example.com"
            assert result.api_token == "test-token"

    def test_get_jira_credentials_missing_env_vars(self):
        """Test getting Jira credentials with missing environment variables."""
        with patch.dict(os.environ, {}, clear=True):
            result = get_jira_credentials()

            assert result is None

    def test_get_jira_credentials_from_config_success(self):
        """Test getting Jira credentials from config."""
        jira_config = JiraConfig(
            base_url="https://config.atlassian.net",
            email="config@example.com",
            api_token="config-token"
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
            base_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test-token"
        )
        org_config = OrganizationConfig(name="test-org", jira=jira_config)
        config = DevHubConfig(
            default_organization="test-org",
            organizations=(org_config,)
        )

        result = resolve_jira_key_with_config(config, branch="feature/TEST-456-implement-feature")

        assert result == "TEST-456"

    def test_resolve_jira_key_with_config_no_match(self):
        """Test resolving Jira key with no match found."""
        config = DevHubConfig()

        result = resolve_jira_key_with_config(config, branch="main")

        assert result is None

    def test_fetch_jira_issue_success(self):
        """Test successful Jira issue fetching."""
        credentials = JiraCredentials(
            base_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test-token"
        )

        mock_response_data = {
            "key": "TEST-123",
            "fields": {
                "summary": "Test issue",
                "description": "Test description"
            }
        }

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

    def test_fetch_jira_issue_http_error(self):
        """Test Jira issue fetching with HTTP error."""
        credentials = JiraCredentials(
            base_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test-token"
        )

        with patch("devhub.main.run_command") as mock_run:
            mock_run.return_value = Failure("HTTP 404: Not Found")

            result = fetch_jira_issue(credentials, "NONEXISTENT-123")

            assert isinstance(result, Failure)
            assert "404" in result.failure()


class TestGitHubFunctions:
    """Test GitHub-related functions."""

    def test_get_repository_info_success(self):
        """Test successful repository info retrieval."""
        mock_repo_data = {
            "owner": {"login": "testorg"},
            "name": "testrepo"
        }

        with patch("devhub.main.run_command") as mock_run:
            mock_process = Mock()
            mock_process.stdout = json.dumps(mock_repo_data)
            mock_run.return_value = Success(mock_process)

            result = get_repository_info()

            assert isinstance(result, Success)
            repo = result.unwrap()
            assert repo.owner == "testorg"
            assert repo.name == "testrepo"

    def test_get_repository_info_command_failure(self):
        """Test repository info retrieval with command failure."""
        with patch("devhub.main.run_command") as mock_run:
            mock_run.return_value = Failure("gh command failed")

            result = get_repository_info()

            assert isinstance(result, Failure)

    def test_get_current_branch_success(self):
        """Test successful current branch retrieval."""
        with patch("devhub.main.run_command") as mock_run:
            mock_process = Mock()
            mock_process.stdout = "feature/test-branch"
            mock_run.return_value = Success(mock_process)

            result = get_current_branch()

            assert isinstance(result, Success)
            assert result.unwrap() == "feature/test-branch"

    def test_get_current_branch_failure(self):
        """Test current branch retrieval failure."""
        with patch("devhub.main.run_command") as mock_run:
            mock_run.return_value = Failure("Not a git repository")

            result = get_current_branch()

            assert isinstance(result, Failure)

    def test_resolve_pr_number_explicit(self):
        """Test PR number resolution with explicit number."""
        repo = Repository(owner="testorg", name="testrepo")

        result = resolve_pr_number(repo, pr_number=123, branch="main", jira_key=None)

        assert isinstance(result, Success)
        assert result.unwrap() == 123

    def test_resolve_pr_number_from_search(self):
        """Test PR number resolution from search results."""
        repo = Repository(owner="testorg", name="testrepo")

        mock_search_data = {
            "items": [{"number": 456, "title": "Test PR"}]
        }

        with patch("devhub.main.run_command") as mock_run:
            mock_process = Mock()
            mock_process.stdout = json.dumps(mock_search_data)
            mock_run.return_value = Success(mock_process)

            result = resolve_pr_number(repo, pr_number=None, branch="main", jira_key="TEST-123")

            assert isinstance(result, Success)
            assert result.unwrap() == 456

    def test_resolve_pr_number_no_results(self):
        """Test PR number resolution with no search results."""
        repo = Repository(owner="testorg", name="testrepo")

        mock_search_data = {"items": []}

        with patch("devhub.main.run_command") as mock_run:
            mock_process = Mock()
            mock_process.stdout = json.dumps(mock_search_data)
            mock_run.return_value = Success(mock_process)

            result = resolve_pr_number(repo, pr_number=None, branch="main", jira_key="NONEXISTENT-123")

            assert isinstance(result, Failure)

    def test_fetch_pr_details_success(self):
        """Test successful PR details fetching."""
        repo = Repository(owner="testorg", name="testrepo")

        mock_pr_data = {
            "number": 123,
            "title": "Test PR",
            "body": "Test description"
        }

        with patch("devhub.main.run_command") as mock_run:
            mock_process = Mock()
            mock_process.stdout = json.dumps(mock_pr_data)
            mock_run.return_value = Success(mock_process)

            result = fetch_pr_details(repo, 123)

            assert isinstance(result, Success)
            pr_data = result.unwrap()
            assert pr_data["number"] == 123
            assert pr_data["title"] == "Test PR"

    def test_fetch_pr_details_failure(self):
        """Test PR details fetching failure."""
        repo = Repository(owner="testorg", name="testrepo")

        with patch("devhub.main.run_command") as mock_run:
            mock_run.return_value = Failure("PR not found")

            result = fetch_pr_details(repo, 999)

            assert isinstance(result, Failure)

    def test_fetch_pr_diff_success(self):
        """Test successful PR diff fetching."""
        mock_diff = "diff --git a/file.py b/file.py\n--- a/file.py\n+++ b/file.py"

        with patch("devhub.main.run_command") as mock_run:
            mock_process = Mock()
            mock_process.stdout = mock_diff
            mock_run.return_value = Success(mock_process)

            result = fetch_pr_diff(123)

            assert isinstance(result, Success)
            assert result.unwrap() == mock_diff

    def test_fetch_pr_diff_failure(self):
        """Test PR diff fetching failure."""
        with patch("devhub.main.run_command") as mock_run:
            mock_run.return_value = Failure("Failed to fetch diff")

            result = fetch_pr_diff(999)

            assert isinstance(result, Failure)

    def test_fetch_unresolved_comments_success(self):
        """Test successful unresolved comments fetching."""
        repo = Repository(owner="testorg", name="testrepo")

        mock_comments = [
            {
                "id": "comment1",
                "body": "This needs improvement",
                "path": "src/main.py",
                "user": {"login": "reviewer1"},
                "created_at": "2024-01-15T10:30:00Z",
                "diff_hunk": "@@ -1,3 +1,3 @@"
            }
        ]

        with patch("devhub.main.run_command") as mock_run:
            mock_process = Mock()
            mock_process.stdout = json.dumps(mock_comments)
            mock_run.return_value = Success(mock_process)

            result = fetch_unresolved_comments(repo, 123, limit=20)

            assert isinstance(result, Success)
            comments = result.unwrap()
            assert len(comments) == 1
            assert comments[0].body == "This needs improvement"
            assert comments[0].author == "reviewer1"

    def test_fetch_unresolved_comments_failure(self):
        """Test unresolved comments fetching failure."""
        repo = Repository(owner="testorg", name="testrepo")

        with patch("devhub.main.run_command") as mock_run:
            mock_run.return_value = Failure("Failed to fetch comments")

            result = fetch_unresolved_comments(repo, 123, limit=20)

            assert isinstance(result, Failure)


class TestBundleOperations:
    """Test bundle creation and handling functions."""

    def test_gather_bundle_data_full_success(self):
        """Test successful bundle data gathering with all components."""
        args = argparse.Namespace(format="json", metadata_only=False)
        bundle_config = BundleConfig(
            include_jira=True,
            include_pr=True,
            include_diff=True,
            include_comments=True,
            limit=20
        )
        repo = Repository(owner="testorg", name="testrepo")
        config = DevHubConfig()

        # Mock all the data fetching functions
        mock_jira_issue = JiraIssue(
            key="TEST-123",
            summary="Test issue",
            description="Test description",
            raw_data={"id": "test-123"}
        )

        mock_pr_data = {"number": 456, "title": "Test PR"}
        mock_diff = "test diff content"
        mock_comments = (
            ReviewComment(
                id="comment1",
                body="Test comment",
                path="test.py",
                author="reviewer",
                created_at="2024-01-01T00:00:00Z",
                diff_hunk="@@ -1,3 +1,3 @@",
                resolved=False
            ),
        )

        with patch("devhub.main.fetch_jira_issue") as mock_fetch_jira, \
                patch("devhub.main.fetch_pr_details") as mock_fetch_pr, \
                patch("devhub.main.fetch_pr_diff") as mock_fetch_diff, \
                patch("devhub.main.fetch_unresolved_comments") as mock_fetch_comments, \
                patch("devhub.main.get_jira_credentials") as mock_get_creds:
            mock_get_creds.return_value = JiraCredentials(
                base_url="https://test.atlassian.net",
                email="test@example.com",
                api_token="test-token"
            )
            mock_fetch_jira.return_value = Success(mock_jira_issue)
            mock_fetch_pr.return_value = Success(mock_pr_data)
            mock_fetch_diff.return_value = Success(mock_diff)
            mock_fetch_comments.return_value = Success(mock_comments)

            result = _gather_bundle_data(
                args, bundle_config, repo, "main", "TEST-123", 456, config
            )

            assert isinstance(result, Success)
            json_data = json.loads(result.unwrap())
            assert json_data["jira"]["key"] == "TEST-123"
            assert json_data["pull_request"]["number"] == 456
            assert json_data["diff"] == mock_diff
            assert len(json_data["comments"]) == 1

    def test_gather_bundle_data_jira_only(self):
        """Test bundle data gathering with Jira only."""
        args = argparse.Namespace(format="json", metadata_only=False)
        bundle_config = BundleConfig(
            include_jira=True,
            include_pr=False,
            include_diff=False,
            include_comments=False
        )
        repo = Repository(owner="testorg", name="testrepo")
        config = DevHubConfig()

        mock_jira_issue = JiraIssue(
            key="TEST-123",
            summary="Test issue",
            description="Test description",
            raw_data={"id": "test-123"}
        )

        with patch("devhub.main.fetch_jira_issue") as mock_fetch_jira, \
                patch("devhub.main.get_jira_credentials") as mock_get_creds:
            mock_get_creds.return_value = JiraCredentials(
                base_url="https://test.atlassian.net",
                email="test@example.com",
                api_token="test-token"
            )
            mock_fetch_jira.return_value = Success(mock_jira_issue)

            result = _gather_bundle_data(
                args, bundle_config, repo, "main", "TEST-123", None, config
            )

            assert isinstance(result, Success)
            json_data = json.loads(result.unwrap())
            assert json_data["jira"]["key"] == "TEST-123"
            assert "pull_request" not in json_data
            assert "diff" not in json_data
            assert "comments" not in json_data

    def test_gather_bundle_data_metadata_only(self):
        """Test bundle data gathering with metadata only."""
        args = argparse.Namespace(format="json", metadata_only=True)
        bundle_config = BundleConfig(
            include_jira=True,
            include_pr=True,
            include_diff=True,
            include_comments=True
        )
        repo = Repository(owner="testorg", name="testrepo")
        config = DevHubConfig()

        result = _gather_bundle_data(
            args, bundle_config, repo, "main", "TEST-123", 456, config
        )

        assert isinstance(result, Success)
        json_data = json.loads(result.unwrap())
        # Should only contain metadata, not actual data
        assert "metadata" in json_data
        assert json_data["metadata"]["repository"]["owner"] == "testorg"
        assert json_data["metadata"]["branch"] == "main"

    def test_handle_bundle_command_success(self):
        """Test successful bundle command handling."""
        args = argparse.Namespace(
            jira_key="TEST-123",
            pr_number=456,
            organization=None,
            no_jira=False,
            no_pr=False,
            no_diff=False,
            no_comments=False,
            limit=20,
            output_dir=None,
            format="files",
            metadata_only=False
        )

        mock_repo = Repository(owner="testorg", name="testrepo")
        mock_bundle_data = '{"test": "data"}'

        with patch("devhub.main.get_repository_info") as mock_get_repo, \
                patch("devhub.main.get_current_branch") as mock_get_branch, \
                patch("devhub.main._gather_bundle_data") as mock_gather, \
                patch("devhub.main.create_output_paths") as mock_create_paths, \
                patch("devhub.main.ensure_directory") as mock_ensure_dir, \
                patch("devhub.main.write_json_file") as mock_write_json:
            mock_get_repo.return_value = Success(mock_repo)
            mock_get_branch.return_value = Success("main")
            mock_gather.return_value = Success(mock_bundle_data)

            mock_paths = MagicMock()
            mock_paths.bundle_json = Path("/test/bundle.json")
            mock_create_paths.return_value = mock_paths

            mock_ensure_dir.return_value = Success(None)
            mock_write_json.return_value = Success(None)

            result = handle_bundle_command(args)

            assert isinstance(result, Success)

    def test_handle_bundle_command_repo_failure(self):
        """Test bundle command handling with repository failure."""
        args = argparse.Namespace(
            jira_key=None,
            pr_number=None,
            organization=None,
            no_jira=False,
            no_pr=False,
            no_diff=False,
            no_comments=False,
            limit=20,
            output_dir=None,
            format="files",
            metadata_only=False
        )

        with patch("devhub.main.get_repository_info") as mock_get_repo:
            mock_get_repo.return_value = Failure("Not a git repository")

            result = handle_bundle_command(args)

            assert isinstance(result, Failure)
            assert "git repository" in result.failure()


class TestMainCLI:
    """Test main CLI entry point."""

    def test_main_bundle_command_success(self):
        """Test main function with bundle command."""
        with patch("devhub.main.handle_bundle_command") as mock_handle:
            mock_handle.return_value = Success("Bundle created successfully")

            result = main(["bundle", "--jira-key", "TEST-123"])

            assert result == 0

    def test_main_bundle_command_failure(self):
        """Test main function with bundle command failure."""
        with patch("devhub.main.handle_bundle_command") as mock_handle:
            mock_handle.return_value = Failure("Bundle creation failed")

            result = main(["bundle"])

            assert result == 1

    def test_main_unknown_command(self):
        """Test main function with unknown command."""
        result = main(["unknown"])

        assert result == 2  # argparse error

    def test_main_version_flag(self):
        """Test main function with version flag."""
        result = main(["--version"])

        assert result == 0

    def test_main_help_flag(self):
        """Test main function with help flag."""
        result = main(["--help"])

        assert result == 0
