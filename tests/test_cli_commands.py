"""Tests for DevHub CLI commands and wizard flows.

These tests cover the CLI commands that weren't covered in other test files.
"""

import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch

import pytest
import yaml
from click.testing import CliRunner

from devhub.cli import cli


class TestCLIInitCommand:
    """Test the init command and its wizard flows."""

    @pytest.fixture
    def cli_runner(self) -> CliRunner:
        """Provide a Click CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def temp_git_repo(self) -> Generator[Path]:
        """Create a temporary git repository."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            git_dir = repo_path / ".git"
            git_dir.mkdir()

            # Create basic git config
            git_config = git_dir / "config"
            git_config.write_text("""[remote "origin"]
    url = https://github.com/testorg/testrepo.git
    fetch = +refs/heads/*:refs/remotes/origin/*
""")
            yield repo_path

    def test_init_basic_flag_github(self, cli_runner: CliRunner, temp_git_repo: Path) -> None:
        """Test init with --basic flag and GitHub setup."""
        import os

        original_cwd = Path.cwd()

        try:
            os.chdir(temp_git_repo)

            # Mock the prompts for configuration
            with patch("click.prompt", side_effect=["testorg", "1", "2"]):  # org, repo platform, PM platform
                result = cli_runner.invoke(cli, ["init", "--basic", "--github"])

                assert result.exit_code == 0
                assert "Created project config" in result.output

                # Check config file was created
                config_file = temp_git_repo / ".devhub.yaml"
                assert config_file.exists()

                # Verify config content
                with config_file.open() as f:
                    config = yaml.safe_load(f)
                    assert config["version"] == "1.0"
                    assert config["github"]["enabled"] is True
                    assert config["github"]["organization"] == "testorg"

        finally:
            os.chdir(original_cwd)

    def test_init_basic_flag_all_platforms(self, cli_runner: CliRunner, temp_git_repo: Path) -> None:
        """Test init with all platform flags."""
        import os

        original_cwd = Path.cwd()

        try:
            os.chdir(temp_git_repo)

            with patch(
                "click.prompt",
                side_effect=[
                    "testorg",  # GitHub org
                    "https://gitlab.company.com",  # GitLab URL
                    "https://company.atlassian.net",  # Jira URL
                    "PROJ",  # Jira project key
                ],
            ):
                result = cli_runner.invoke(
                    cli, ["init", "--basic", "--github", "--gitlab", "--jira", "--github-projects"]
                )

                assert result.exit_code == 0

                config_file = temp_git_repo / ".devhub.yaml"
                with config_file.open() as f:
                    config = yaml.safe_load(f)
                    assert config["github"]["enabled"] is True
                    assert config["gitlab"]["enabled"] is True
                    assert config["jira"]["enabled"] is True
                    assert config["github"]["projects"] is True

        finally:
            os.chdir(original_cwd)

    def test_init_with_profile(self, cli_runner: CliRunner, temp_git_repo: Path) -> None:
        """Test init with a profile."""
        import os

        original_cwd = Path.cwd()

        try:
            os.chdir(temp_git_repo)

            # Mock profile loading to return a config
            mock_profile_config = {
                "version": "1.0",
                "github": {"enabled": True, "organization": "profile-org"},
                "jira": {"enabled": False},
            }

            with patch("devhub.cli._load_profile_config", return_value=mock_profile_config):
                result = cli_runner.invoke(cli, ["init", "--basic", "--profile", "work"])

                assert result.exit_code == 0

                config_file = temp_git_repo / ".devhub.yaml"
                with config_file.open() as f:
                    config = yaml.safe_load(f)
                    assert config["github"]["organization"] == "profile-org"

        finally:
            os.chdir(original_cwd)

    @patch("devhub.cli._detect_repository_platform")
    @patch("devhub.cli._detect_project_type")
    def test_init_wizard_flow_github(
        self, mock_project_types: Mock, mock_detect_platform: Mock, cli_runner: CliRunner, temp_git_repo: Path
    ) -> None:
        """Test the complete init wizard flow with GitHub."""
        import os

        original_cwd = Path.cwd()

        try:
            os.chdir(temp_git_repo)

            # Mock detection results
            mock_detect_platform.return_value = ("github", {"organization": "testorg", "repository": "testrepo"})
            mock_project_types.return_value = ["Python", "Node.js"]

            # Mock wizard steps
            with (
                patch("devhub.cli._wizard_select_platforms") as mock_platforms,
                patch("devhub.cli._wizard_advanced_config") as mock_advanced,
                patch("devhub.cli._wizard_build_config") as mock_build,
                patch("devhub.cli._wizard_setup_credentials") as mock_creds,
                patch("devhub.cli._wizard_show_summary") as mock_summary,
                patch("click.confirm", return_value=True),  # Setup credentials
            ):
                # Configure mocks
                mock_platforms.return_value = {"repository": "github", "project_management": "jira"}
                mock_advanced.return_value = {"advanced": "config"}
                mock_build.return_value = {"version": "1.0", "built": True}

                result = cli_runner.invoke(cli, ["init"])

                # Verify wizard was called
                assert result.exit_code == 0
                assert "DevHub Complete Setup Wizard" in result.output
                assert "Setup Complete!" in result.output

                # Verify functions were called
                mock_platforms.assert_called_once()
                mock_advanced.assert_called_once()
                mock_build.assert_called_once()
                mock_creds.assert_called_once()
                mock_summary.assert_called_once()

        finally:
            os.chdir(original_cwd)


class TestCLIAuthCommands:
    """Test authentication management commands."""

    @pytest.fixture
    def cli_runner(self) -> CliRunner:
        """Provide a Click CLI test runner."""
        return CliRunner()

    @patch("devhub.cli.load_config")
    @patch("devhub.cli.VAULT_DIR")
    def test_auth_status_command(self, mock_vault_dir: Mock, mock_load_config: Mock, cli_runner: CliRunner) -> None:
        """Test auth status command with configured platforms."""
        # Mock vault initialized
        mock_vault_dir.__truediv__.return_value.exists.return_value = True

        # Mock config with platforms enabled
        mock_config = {"github": {"enabled": True}, "jira": {"enabled": True}}
        mock_load_config.return_value = mock_config

        result = cli_runner.invoke(cli, ["auth", "status"])

        assert result.exit_code == 0
        assert "Authentication Status" in result.output
        assert "Credential vault initialized" in result.output
        assert "Configured platforms: GitHub, Jira" in result.output

    @patch("devhub.cli.load_config")
    @patch("devhub.cli.VAULT_DIR")
    def test_auth_status_no_platforms(
        self, mock_vault_dir: Mock, mock_load_config: Mock, cli_runner: CliRunner
    ) -> None:
        """Test auth status when no platforms are configured."""
        # Mock vault initialized
        mock_vault_dir.__truediv__.return_value.exists.return_value = True

        # Mock config with no platforms
        mock_config = {"github": {"enabled": False}, "jira": {"enabled": False}}
        mock_load_config.return_value = mock_config

        result = cli_runner.invoke(cli, ["auth", "status"])

        assert result.exit_code == 0
        assert "No platforms configured" in result.output

    @patch("devhub.cli.load_config", return_value={})
    @patch("devhub.cli.VAULT_DIR")
    def test_auth_status_vault_not_initialized(
        self,
        mock_vault_dir: Mock,
        _mock_load_config: Mock,  # noqa: PT019
        cli_runner: CliRunner,
    ) -> None:
        """Test auth status when vault is not initialized."""
        # Mock vault not initialized
        mock_vault_dir.__truediv__.return_value.exists.return_value = False

        result = cli_runner.invoke(cli, ["auth", "status"])

        assert result.exit_code == 0
        assert "Credential vault not initialized" in result.output
        assert "Run: devhub auth setup" in result.output

    # Note: auth setup tests are complex due to async nature and are covered in integration tests


class TestCLIClaudeCommands:
    """Test Claude integration commands."""

    @pytest.fixture
    def cli_runner(self) -> CliRunner:
        """Provide a Click CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def temp_git_repo(self) -> Generator[Path]:
        """Create a temporary git repository."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            git_dir = repo_path / ".git"
            git_dir.mkdir()
            yield repo_path

    @patch("devhub.cli.claude_code_review_context")
    def test_claude_context_command_success(
        self, mock_context_func: Mock, cli_runner: CliRunner, temp_git_repo: Path
    ) -> None:
        """Test claude context command success."""
        import os

        from returns.result import Success

        original_cwd = Path.cwd()

        try:
            os.chdir(temp_git_repo)

            # Mock successful context generation
            mock_context_func.return_value = Success("# Claude Context\n\nThis is test context content.")

            result = cli_runner.invoke(cli, ["claude", "context"])

            assert result.exit_code == 0
            assert "Generating enhanced Claude context" in result.output
            assert "Context saved to:" in result.output

            # Check context file was created
            context_file = temp_git_repo / "claude_context.md"
            assert context_file.exists()
            assert "This is test context content" in context_file.read_text()

        finally:
            os.chdir(original_cwd)

    @patch("devhub.cli.claude_code_review_context")
    def test_claude_context_command_failure(
        self, mock_context_func: Mock, cli_runner: CliRunner, temp_git_repo: Path
    ) -> None:
        """Test claude context command failure."""
        import os

        from returns.result import Failure

        original_cwd = Path.cwd()

        try:
            os.chdir(temp_git_repo)

            # Mock failed context generation
            mock_context_func.return_value = Failure("Context generation failed")

            result = cli_runner.invoke(cli, ["claude", "context"])

            # The actual implementation catches errors and continues with exit code 0
            assert result.exit_code == 0
            assert "Context generation failed" in result.output

        finally:
            os.chdir(original_cwd)

    # Note: Claude context command doesn't support --output flag, removing this test


class TestCLIProjectStatusCommand:
    """Test project status command."""

    @pytest.fixture
    def cli_runner(self) -> CliRunner:
        """Provide a Click CLI test runner."""
        return CliRunner()

    def test_project_status_basic(self, cli_runner: CliRunner) -> None:
        """Test basic project status command."""
        result = cli_runner.invoke(cli, ["project-status"])

        assert result.exit_code == 0
        assert "DevHub Status" in result.output
        assert "Project Detection:" in result.output

    # Note: Detailed project status tests require complex mocking and are covered in integration tests


class TestCLIDoctorCommand:
    """Test doctor command."""

    @pytest.fixture
    def cli_runner(self) -> CliRunner:
        """Provide a Click CLI test runner."""
        return CliRunner()

    @patch("subprocess.run")
    @patch("devhub.cli._detect_repository_platform")
    def test_doctor_command_all_good(
        self, mock_detect_platform: Mock, mock_subprocess: Mock, cli_runner: CliRunner
    ) -> None:
        """Test doctor command when everything is working."""
        # Mock git repository detection
        mock_detect_platform.return_value = ("github", {"organization": "testorg"})

        # Mock subprocess calls for command checks
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = "git version 2.34.1"

        result = cli_runner.invoke(cli, ["doctor"])

        assert result.exit_code == 0
        assert "DevHub Doctor - System Health Check" in result.output
        assert "✅ git is available" in result.output
        assert "✅ Current directory is a git repository" in result.output

    @patch("subprocess.run")
    @patch("devhub.cli._detect_repository_platform")
    def test_doctor_command_git_missing(
        self, mock_detect_platform: Mock, mock_subprocess: Mock, cli_runner: CliRunner
    ) -> None:
        """Test doctor command when git is missing."""
        mock_detect_platform.return_value = ("none", {})

        # Mock git command not found
        mock_subprocess.side_effect = FileNotFoundError()

        result = cli_runner.invoke(cli, ["doctor"])

        assert result.exit_code == 0
        assert "❌ git is not available" in result.output
        assert "⚠️  Current directory is not a git repository" in result.output

    @patch("subprocess.run")
    @patch("devhub.cli._detect_repository_platform")
    def test_doctor_command_git_error(
        self, mock_detect_platform: Mock, mock_subprocess: Mock, cli_runner: CliRunner
    ) -> None:
        """Test doctor command when git command fails."""
        mock_detect_platform.return_value = ("git", {})

        # Mock git command failure
        mock_subprocess.return_value.returncode = 1

        result = cli_runner.invoke(cli, ["doctor"])

        assert result.exit_code == 0
        assert "❌ git is not available" in result.output


class TestCLIBundleCommand:
    """Test bundle command integration."""

    @pytest.fixture
    def cli_runner(self) -> CliRunner:
        """Provide a Click CLI test runner."""
        return CliRunner()

    @patch("devhub.cli.handle_bundle_command")
    def test_bundle_command_success(self, mock_handle_bundle: Mock, cli_runner: CliRunner) -> None:
        """Test successful bundle command."""
        from returns.result import Success

        mock_handle_bundle.return_value = Success("Bundle created successfully")

        result = cli_runner.invoke(cli, ["bundle", "--claude"])

        assert result.exit_code == 0
        mock_handle_bundle.assert_called_once()

    @patch("devhub.cli.handle_bundle_command")
    def test_bundle_command_failure(self, mock_handle_bundle: Mock, cli_runner: CliRunner) -> None:
        """Test failed bundle command."""
        from returns.result import Failure

        mock_handle_bundle.return_value = Failure("Bundle creation failed")

        result = cli_runner.invoke(cli, ["bundle", "--claude"])

        assert result.exit_code == 1
        assert "Bundle creation failed" in result.output
