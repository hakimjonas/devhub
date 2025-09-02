"""Integration tests for DevHub CLI workflows."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from returns.result import Failure
from returns.result import Success

from devhub.main import JiraCredentials
from devhub.main import Repository
from devhub.main import ReviewComment
from devhub.main import fetch_jira_issue
from devhub.main import fetch_pr_details
from devhub.main import fetch_unresolved_comments
from devhub.main import get_current_branch
from devhub.main import get_repository_info
from devhub.main import handle_bundle_command
from devhub.main import main


@pytest.fixture
def mock_jira_credentials() -> JiraCredentials:
    """Provide mock Jira credentials for testing."""
    return JiraCredentials(base_url="https://test.atlassian.net", email="test@example.com", api_token="test-token")


@pytest.fixture
def mock_repository() -> Repository:
    """Provide mock repository for testing."""
    return Repository(owner="testorg", name="testrepo")


@pytest.fixture
def mock_review_comments() -> tuple[ReviewComment, ...]:
    """Provide mock review comments for testing."""
    return (
        ReviewComment(
            id="comment1",
            body="This needs improvement",
            path="src/main.py",
            author="reviewer1",
            created_at="2024-01-15T10:30:00Z",
            diff_hunk="@@ -1,3 +1,3 @@",
            resolved=False,
        ),
        ReviewComment(
            id="comment2",
            body="Good catch!",
            path=None,
            author="reviewer2",
            created_at="2024-01-15T11:00:00Z",
            diff_hunk=None,
            resolved=False,
        ),
    )


class TestGitHubIntegration:
    """Integration tests for GitHub API interactions."""

    @patch("devhub.main.run_command")
    def test_get_repository_info_success(self, mock_run_command: Mock) -> None:
        """Test successful repository info retrieval."""
        # Mock command existence check
        mock_run_command.side_effect = [
            Success(MagicMock(stdout="/usr/local/bin/gh")),  # gh exists
            Success(MagicMock(stdout='{"owner":{"login":"testorg"},"name":"testrepo"}')),
        ]

        result = get_repository_info()

        assert isinstance(result, Success)
        repo = result.unwrap()
        assert repo.owner == "testorg"
        assert repo.name == "testrepo"

    @patch("devhub.main.run_command")
    def test_get_repository_info_command_not_found(self, mock_run_command: Mock) -> None:
        """Test repository info when gh command not found."""
        mock_run_command.return_value = Failure("Command not found")

        result = get_repository_info()

        assert isinstance(result, Failure)
        assert "Command not found" in result.failure()

    @patch("devhub.main.run_command")
    def test_get_current_branch_success(self, mock_run_command: Mock) -> None:
        """Test successful branch retrieval."""
        mock_run_command.return_value = Success(MagicMock(stdout="feature/ABC-123-test\n"))

        result = get_current_branch()

        assert isinstance(result, Success)
        assert result.unwrap() == "feature/ABC-123-test"

    @patch("devhub.main.run_command")
    def test_fetch_pr_details_success(self, mock_run_command: Mock, mock_repository: Repository) -> None:
        """Test successful PR details fetching."""
        pr_data = {"number": 123, "title": "Test PR", "body": "Test description", "head": {"ref": "feature/test"}}
        mock_run_command.return_value = Success(MagicMock(stdout=json.dumps(pr_data)))

        result = fetch_pr_details(mock_repository, 123)

        assert isinstance(result, Success)
        data = result.unwrap()
        assert data["number"] == 123
        assert data["title"] == "Test PR"

    @patch("devhub.main.run_command")
    def test_fetch_unresolved_comments_success(self, mock_run_command: Mock, mock_repository: Repository) -> None:
        """Test successful unresolved comments fetching."""
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
                                                "path": "src/main.py",
                                                "createdAt": "2024-01-15T10:30:00Z",
                                                "author": {"login": "reviewer1"},
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
        mock_run_command.return_value = Success(MagicMock(stdout=json.dumps(graphql_response)))

        result = fetch_unresolved_comments(mock_repository, 123, 10)

        assert isinstance(result, Success)
        comments = result.unwrap()
        assert len(comments) == 1
        assert comments[0].id == "comment1"
        assert comments[0].body == "Test comment"


class TestJiraIntegration:
    """Integration tests for Jira API interactions."""

    @patch("devhub.main.urllib.request.urlopen")
    def test_fetch_jira_issue_success(self, mock_urlopen: Mock, mock_jira_credentials: JiraCredentials) -> None:
        """Test successful Jira issue fetching."""
        jira_response = {"key": "ABC-123", "fields": {"summary": "Test issue", "description": "Test description"}}

        # Mock the response
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(jira_response).encode()
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        result = fetch_jira_issue(mock_jira_credentials, "ABC-123")

        assert isinstance(result, Success)
        issue = result.unwrap()
        assert issue.key == "ABC-123"
        assert issue.summary == "Test issue"
        assert issue.description == "Test description"

    @patch("devhub.main.urllib.request.urlopen")
    def test_fetch_jira_issue_http_error(self, mock_urlopen: Mock, mock_jira_credentials: JiraCredentials) -> None:
        """Test Jira issue fetching with HTTP error."""
        from urllib.error import HTTPError

        mock_urlopen.side_effect = HTTPError(url="test", code=404, msg="Not Found", hdrs=None, fp=None)  # type: ignore[arg-type]

        result = fetch_jira_issue(mock_jira_credentials, "ABC-123")

        assert isinstance(result, Failure)
        assert "HTTP error 404" in result.failure()


class TestCLIIntegration:
    """Integration tests for complete CLI workflows."""

    @patch("devhub.main.assert_git_repo")
    @patch("devhub.main.get_repository_info")
    @patch("devhub.main.get_current_branch")
    @patch("devhub.main.find_pr_by_branch")
    @patch("devhub.main.get_jira_credentials")
    @patch("devhub.main.fetch_jira_issue")
    @patch("devhub.main.fetch_pr_details")
    @patch("devhub.main.fetch_unresolved_comments")
    @patch("devhub.main.ensure_directory")
    @patch("devhub.main.write_json_file")
    @patch("devhub.main.write_text_file")
    def test_bundle_command_full_workflow(
        self,
        mock_write_text: Mock,
        mock_write_json: Mock,
        mock_ensure_dir: Mock,
        mock_fetch_comments: Mock,
        mock_fetch_pr: Mock,
        mock_fetch_jira: Mock,
        mock_get_creds: Mock,
        mock_find_pr: Mock,
        mock_get_branch: Mock,
        mock_get_repo: Mock,
        mock_assert_git: Mock,
        mock_repository: Repository,
        mock_jira_credentials: JiraCredentials,
        mock_review_comments: tuple[ReviewComment, ...],
    ) -> None:
        """Test complete bundle command workflow."""
        # Setup mocks
        mock_assert_git.return_value = Success(None)
        mock_get_repo.return_value = Success(mock_repository)
        mock_get_branch.return_value = Success("feature/ABC-123-test")
        mock_find_pr.return_value = Success(123)
        mock_get_creds.return_value = mock_jira_credentials

        # Mock Jira issue
        from devhub.main import JiraIssue

        mock_jira_issue = JiraIssue(
            key="ABC-123",
            summary="Test issue",
            description="Test description",
            raw_data={"key": "ABC-123", "fields": {"summary": "Test issue"}},
        )
        mock_fetch_jira.return_value = Success(mock_jira_issue)

        # Mock PR details
        pr_data = {"number": 123, "title": "Test PR", "body": "Test body"}
        mock_fetch_pr.return_value = Success(pr_data)

        # Mock comments
        mock_fetch_comments.return_value = Success(mock_review_comments)

        # Mock file operations
        mock_ensure_dir.return_value = Success(None)
        mock_write_json.return_value = Success(None)
        mock_write_text.return_value = Success(None)

        # Create mock args
        mock_args = Mock()
        mock_args.out = None
        mock_args.branch = None
        mock_args.jira_key = None
        mock_args.pr = None
        mock_args.limit = 10
        mock_args.no_jira = False
        mock_args.no_pr = False
        mock_args.no_diff = True  # Skip diff to avoid additional mocking
        mock_args.no_comments = False
        mock_args.format = "files"  # Use file-based output format
        mock_args.stdout = False
        mock_args.metadata_only = False

        result = handle_bundle_command(mock_args)

        assert isinstance(result, Success)
        assert "Bundle saved to:" in result.unwrap()

        # Verify calls were made
        mock_assert_git.assert_called_once()
        mock_get_repo.assert_called_once()
        mock_get_branch.assert_called_once()
        mock_fetch_jira.assert_called_once()
        mock_fetch_pr.assert_called_once()
        mock_fetch_comments.assert_called_once()

    def test_main_bundle_command_success(self) -> None:
        """Test main function with bundle command success."""
        with patch("devhub.main.handle_bundle_command") as mock_handle:
            mock_handle.return_value = Success("Bundle saved successfully")

            result = main(["bundle", "--no-jira", "--no-pr", "--no-comments"])

            assert result == 0

    def test_main_bundle_command_failure(self) -> None:
        """Test main function with bundle command failure."""
        with patch("devhub.main.handle_bundle_command") as mock_handle:
            mock_handle.return_value = Failure("Test error")

            with patch("sys.stderr") as mock_stderr:
                result = main(["bundle"])

                assert result == 1
                mock_stderr.write.assert_called_with("Error: Test error\n")

    def test_main_unknown_command(self) -> None:
        """Test main function with unknown command."""
        result = main(["unknown"])

        # argparse exits with code 2 for invalid arguments
        assert result == 2


class TestEndToEndScenarios:
    """End-to-end scenario tests."""

    @patch("devhub.main.subprocess.run")
    def test_git_repo_check_success(self, mock_subprocess: Mock) -> None:
        """Test git repository check succeeds."""
        mock_subprocess.return_value = MagicMock(stdout="true", returncode=0)

        from devhub.main import assert_git_repo

        result = assert_git_repo()

        assert isinstance(result, Success)

    @patch("devhub.main.subprocess.run")
    def test_git_repo_check_failure(self, mock_subprocess: Mock) -> None:
        """Test git repository check fails."""
        mock_subprocess.side_effect = subprocess.CalledProcessError(1, "git")

        from devhub.main import assert_git_repo

        result = assert_git_repo()

        assert isinstance(result, Failure)

    @patch("devhub.main.Path.mkdir")
    @patch("devhub.main.Path.write_text")
    def test_file_operations_success(self, mock_write_text: Mock, mock_mkdir: Mock) -> None:
        """Test file operations succeed."""
        from devhub.main import ensure_directory
        from devhub.main import write_text_file

        mock_mkdir.return_value = None
        mock_write_text.return_value = None

        # Test directory creation
        result = ensure_directory(Path("/test/path"))
        assert isinstance(result, Success)

        # Test file writing
        result = write_text_file(Path("/test/file.txt"), "test content")
        assert isinstance(result, Success)

    @patch("devhub.main.Path.mkdir")
    def test_file_operations_failure(self, mock_mkdir: Mock) -> None:
        """Test file operations handle failures."""
        from devhub.main import ensure_directory

        mock_mkdir.side_effect = OSError("Permission denied")

        result = ensure_directory(Path("/test/path"))
        assert isinstance(result, Failure)
        assert "Permission denied" in result.failure()


@pytest.mark.integration
class TestRealWorldScenarios:
    """Real-world scenario tests with mocked external dependencies."""

    @patch.dict(
        "os.environ",
        {
            "JIRA_BASE_URL": "https://test.atlassian.net",
            "JIRA_EMAIL": "test@example.com",
            "JIRA_API_TOKEN": "test-token",
        },
    )
    def test_jira_credentials_from_environment(self) -> None:
        """Test Jira credentials loading from environment."""
        from devhub.main import get_jira_credentials

        creds = get_jira_credentials()

        assert creds is not None
        assert creds.base_url == "https://test.atlassian.net"
        assert creds.email == "test@example.com"
        assert creds.api_token == "test-token"

    def test_jira_credentials_missing_environment(self) -> None:
        """Test Jira credentials when environment variables are missing."""
        from devhub.main import get_jira_credentials

        with patch.dict("os.environ", {}, clear=True):
            creds = get_jira_credentials()
            assert creds is None

    @patch("devhub.main.run_command")
    def test_pr_resolution_priority(self, mock_run_command: Mock, mock_repository: Repository) -> None:
        """Test PR number resolution priority order."""
        from devhub.main import resolve_pr_number

        # Direct PR number should take priority
        result = resolve_pr_number(mock_repository, 123, "feature/branch", "ABC-456")
        assert isinstance(result, Success)
        assert result.unwrap() == 123

        # Branch lookup should be second priority
        mock_run_command.return_value = Success(MagicMock(stdout="789\n"))
        result = resolve_pr_number(mock_repository, None, "feature/branch", "ABC-456")
        assert isinstance(result, Success)
        assert result.unwrap() == 789

    def test_output_path_generation_scenarios(self) -> None:
        """Test various output path generation scenarios."""
        from devhub.main import create_output_paths

        with patch("devhub.main.now_slug", return_value="20240115-143045"):
            # Custom output directory
            paths = create_output_paths("/custom", None, None)
            assert str(paths.base_dir) == "/custom"

            # Jira key priority
            paths = create_output_paths(None, "ABC-123", 456)
            assert "ABC-123-20240115-143045" in str(paths.base_dir)

            # PR number fallback
            paths = create_output_paths(None, None, 456)
            assert "pr-456-20240115-143045" in str(paths.base_dir)

            # Default fallback
            paths = create_output_paths(None, None, None)
            assert "bundle-20240115-143045" in str(paths.base_dir)
