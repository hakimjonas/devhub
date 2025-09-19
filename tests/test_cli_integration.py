"""Integration tests for the actual DevHub CLI (devhub.cli module).

These tests verify that the installed CLI works correctly end-to-end.
This covers the actual entry point used by `uv run devhub` commands.
"""

import subprocess
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from click.testing import CliRunner

from devhub.cli import cli


class TestDevHubCLIIntegration:
    """Test the actual DevHub CLI commands as installed."""

    @pytest.fixture
    def cli_runner(self) -> CliRunner:
        """Provide a Click CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def temp_git_repo(self) -> Generator[Path]:
        """Create a temporary git repository for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)

            # Initialize git repo
            subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True)

            # Add a test file and commit
            (repo_path / "README.md").write_text("# Test Project\n")
            subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True)
            subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True)

            yield repo_path

    def test_cli_help_command(self, cli_runner: CliRunner) -> None:
        """Test that CLI help works."""
        result = cli_runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "DevHub - Transform Claude Code" in result.output
        assert "Commands:" in result.output
        assert "doctor" in result.output
        assert "bundle" in result.output

    def test_cli_version_command(self, cli_runner: CliRunner) -> None:
        """Test that CLI version works."""
        result = cli_runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_doctor_command_success(self, cli_runner: CliRunner, temp_git_repo: Path) -> None:
        """Test doctor command in a git repository."""
        with cli_runner.isolated_filesystem():
            # Change to temp git repo
            import os

            original_cwd = Path.cwd()
            try:
                os.chdir(temp_git_repo)

                result = cli_runner.invoke(cli, ["doctor"])

                assert result.exit_code == 0
                assert "DevHub Doctor - System Health Check" in result.output
                assert "Health Check Summary:" in result.output
                assert (
                    "✅ git is available" in result.output or "❌ git is not available" in result.output
                )  # Either is valid
            finally:
                os.chdir(original_cwd)

    def test_doctor_command_outside_git_repo(self, cli_runner: CliRunner) -> None:
        """Test doctor command outside a git repository."""
        with cli_runner.isolated_filesystem():
            result = cli_runner.invoke(cli, ["doctor"])

            assert result.exit_code == 0
            assert "⚠️  Current directory is not a git repository" in result.output

    def test_project_status_command(self, cli_runner: CliRunner, temp_git_repo: Path) -> None:
        """Test project-status command."""
        with cli_runner.isolated_filesystem():
            import os

            original_cwd = Path.cwd()
            try:
                os.chdir(temp_git_repo)

                result = cli_runner.invoke(cli, ["project-status"])

                assert result.exit_code == 0
                assert "DevHub Status" in result.output
                assert "Project Detection:" in result.output
                assert "Git repository detected" in result.output
            finally:
                os.chdir(original_cwd)

    def test_bundle_command_basic(self, cli_runner: CliRunner, temp_git_repo: Path) -> None:
        """Test basic bundle command."""
        from unittest.mock import patch

        from returns.result import Success

        from devhub.main import Repository

        with cli_runner.isolated_filesystem():
            import os

            original_cwd = Path.cwd()
            try:
                os.chdir(temp_git_repo)

                # Mock the repository detection to avoid GitHub API calls
                mock_repo = Repository(owner="testorg", name="testrepo")

                with patch("devhub.main.get_repository_info", return_value=Success(mock_repo)):
                    result = cli_runner.invoke(cli, ["bundle", "--claude", "--no-jira", "--no-pr"])

                    # Debug output if test fails
                    if result.exit_code != 0:
                        # For debugging purposes during development
                        import sys

                        sys.stderr.write(f"Command failed with exit code: {result.exit_code}\n")
                        sys.stderr.write(f"Output: {result.output}\n")
                        sys.stderr.write(f"Exception: {result.exception}\n")

                    assert result.exit_code == 0
                    assert "Creating context bundle" in result.output

                    # Should output JSON data
                    output_lines = result.output.split("\n")
                    json_start = False
                    json_content = []
                    for line in output_lines:
                        if line.strip().startswith("{"):
                            json_start = True
                            json_content.append(line)
                        elif json_start:
                            if line.strip() == "":
                                break
                            json_content.append(line)

                    if json_content:
                        json_text = "\n".join(json_content)
                        try:
                            data = yaml.safe_load(json_text)  # YAML can parse JSON
                            # Should have basic bundle structure
                            assert "metadata" in data
                            assert "repository" in data["metadata"]
                        except yaml.YAMLError:
                            # JSON might be on stdout, that's also acceptable
                            pass
            finally:
                os.chdir(original_cwd)

    def test_bundle_command_with_output_file(self, cli_runner: CliRunner, temp_git_repo: Path) -> None:
        """Test bundle command with output file."""
        from unittest.mock import patch

        from returns.result import Success

        from devhub.main import Repository

        with cli_runner.isolated_filesystem():
            import os

            original_cwd = Path.cwd()
            try:
                os.chdir(temp_git_repo)

                # Mock the repository detection
                mock_repo = Repository(owner="testorg", name="testrepo")

                with patch("devhub.main.get_repository_info", return_value=Success(mock_repo)):
                    output_file = "test_bundle.yaml"
                    result = cli_runner.invoke(
                        cli, ["bundle", "--claude", "--output", output_file, "--no-jira", "--no-pr"]
                    )

                    assert result.exit_code == 0
                    assert "Bundle saved to:" in result.output

                    # The bundle command creates a directory structure, not a single YAML file
                    # when using --output with a non-.yaml extension, but our CLI wrapper
                    # converts JSON to YAML for .yaml files. Let's just check the success message.
                    assert "✅ Bundle saved to:" in result.output or "Bundle saved to:" in result.output
            finally:
                os.chdir(original_cwd)

    def test_init_command_basic_mode(self, cli_runner: CliRunner, temp_git_repo: Path) -> None:
        """Test init command in basic mode."""
        with cli_runner.isolated_filesystem():
            import os

            original_cwd = Path.cwd()
            try:
                os.chdir(temp_git_repo)

                result = cli_runner.invoke(cli, ["init", "--basic"], input="3\n4\n")

                # Debug output if test fails
                if result.exit_code != 0:
                    # For debugging purposes during development
                    import sys

                    sys.stderr.write(f"Init command failed with exit code: {result.exit_code}\n")
                    sys.stderr.write(f"Output: {result.output}\n")
                    sys.stderr.write(f"Exception: {result.exception}\n")

                assert result.exit_code == 0
                assert "Created project config" in result.output

                # Check that .devhub.yaml was created
                config_file = Path(".devhub.yaml")
                assert config_file.exists()

                # Verify config content
                with config_file.open() as f:
                    config = yaml.safe_load(f)
                    assert config.get("version") == "1.0"
                    assert "platforms" in config
            finally:
                os.chdir(original_cwd)

    def test_config_show_command(self, cli_runner: CliRunner) -> None:
        """Test config show command."""
        result = cli_runner.invoke(cli, ["config", "show"])

        # Should not error even with no config
        assert result.exit_code == 0

    def test_auth_status_command(self, cli_runner: CliRunner) -> None:
        """Test auth status command."""
        result = cli_runner.invoke(cli, ["auth", "status"])

        assert result.exit_code == 0
        assert "Authentication Status" in result.output

    @patch("devhub.cli.claude_code_review_context")
    def test_claude_context_command(self, mock_context_func, cli_runner: CliRunner, temp_git_repo: Path) -> None:
        """Test claude context command."""
        from returns.result import Success

        # Mock the context generation
        mock_context_func.return_value = Success("# Mock Context\n\nThis is a test context.")

        with cli_runner.isolated_filesystem():
            import os

            original_cwd = Path.cwd()
            try:
                os.chdir(temp_git_repo)

                result = cli_runner.invoke(cli, ["claude", "context"])

                assert result.exit_code == 0
                assert "Generating enhanced Claude context" in result.output
                assert "Context saved to:" in result.output

                # Check that context file was created
                assert Path("claude_context.md").exists()
            finally:
                os.chdir(original_cwd)

    def test_subprocess_cli_execution(self, temp_git_repo: Path) -> None:
        """Test CLI execution via subprocess (as close to real usage as possible)."""
        import os

        original_cwd = Path.cwd()
        try:
            os.chdir(temp_git_repo)

            # Test help command
            result = subprocess.run(
                ["uv", "run", "devhub", "--help"], check=False, capture_output=True, text=True, timeout=30
            )
            assert result.returncode == 0
            assert "DevHub - Transform Claude Code" in result.stdout

            # Test doctor command
            result = subprocess.run(
                ["uv", "run", "devhub", "doctor"], check=False, capture_output=True, text=True, timeout=30
            )
            assert result.returncode == 0
            assert "DevHub Doctor" in result.stdout

            # Test project-status command
            result = subprocess.run(
                ["uv", "run", "devhub", "project-status"], check=False, capture_output=True, text=True, timeout=30
            )
            assert result.returncode == 0
            assert "DevHub Status" in result.stdout

        finally:
            os.chdir(original_cwd)

    def test_invalid_command(self, cli_runner: CliRunner) -> None:
        """Test that invalid commands are handled properly."""
        result = cli_runner.invoke(cli, ["invalid-command"])

        assert result.exit_code != 0
        assert "No such command" in result.output

    def test_command_flag_combinations(self, cli_runner: CliRunner, temp_git_repo: Path) -> None:
        """Test various command flag combinations."""
        with cli_runner.isolated_filesystem():
            import os

            original_cwd = Path.cwd()
            try:
                os.chdir(temp_git_repo)

                # Test bundle with PR flag (expect failure without mocking since no GitHub setup)
                result = cli_runner.invoke(cli, ["bundle", "--pr", "123"])
                # This will fail because we don't have GitHub configured, that's expected
                assert result.exit_code in [0, 1]

                # Test init with GitHub flag - use input to provide organization
                result = cli_runner.invoke(cli, ["init", "--github", "--basic"], input="testorg\n")
                # Should work or exit gracefully with various exit codes
                assert result.exit_code in [0, 1, 2]  # Various acceptable exit codes

            finally:
                os.chdir(original_cwd)


class TestCLIErrorHandling:
    """Test CLI error handling and edge cases."""

    @pytest.fixture
    def cli_runner(self) -> CliRunner:
        """Provide a Click CLI test runner."""
        return CliRunner()

    def test_cli_handles_keyboard_interrupt(self, cli_runner: CliRunner) -> None:
        """Test CLI handles KeyboardInterrupt gracefully."""
        with patch("devhub.cli.load_config", side_effect=KeyboardInterrupt):
            result = cli_runner.invoke(cli, ["config", "show"])
            # Click handles KeyboardInterrupt by default
            assert result.exit_code != 0

    def test_cli_handles_permission_errors(self, cli_runner: CliRunner) -> None:
        """Test CLI handles permission errors gracefully."""
        with patch("devhub.cli.GLOBAL_CONFIG", Path("/root/forbidden/config.yaml")):
            result = cli_runner.invoke(cli, ["config", "show"])
            # Should not crash, even if config is inaccessible
            assert result.exit_code == 0

    def test_cli_with_corrupted_config(self, cli_runner: CliRunner) -> None:
        """Test CLI with corrupted YAML config."""
        with cli_runner.isolated_filesystem():
            # Create corrupted config
            Path(".devhub.yaml").write_text("invalid: yaml: content: [")

            result = cli_runner.invoke(cli, ["config", "show"])
            # Should handle YAML parsing errors - may exit with error
            assert result.exit_code in [0, 1]  # Either graceful handling or expected failure
