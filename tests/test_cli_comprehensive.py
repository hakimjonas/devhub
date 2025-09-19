"""Comprehensive tests for DevHub CLI module.

These tests cover all CLI functions and commands to achieve 90%+ coverage.
"""

from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch

import pytest
import yaml
from click.testing import CliRunner

from devhub.cli import _create_config_from_flags
from devhub.cli import _create_project_config
from devhub.cli import _detect_project_type
from devhub.cli import _detect_repository_platform
from devhub.cli import _display_detection_results
from devhub.cli import _get_user_choice
from devhub.cli import _load_profile_config
from devhub.cli import _parse_git_remote_info
from devhub.cli import _prompt_platform_selection
from devhub.cli import _prompt_project_management
from devhub.cli import _prompt_repository_platform
from devhub.cli import cli
from devhub.cli import ensure_devhub_home
from devhub.cli import load_config
from devhub.cli import save_global_config


class TestCLIUtilityFunctions:
    """Test CLI utility functions."""

    def test_ensure_devhub_home_creates_directories(self, tmp_path: Path) -> None:
        """Test that ensure_devhub_home creates required directories."""
        with (
            patch("devhub.cli.DEVHUB_HOME", tmp_path),
            patch("devhub.cli.VAULT_DIR", tmp_path / "vault"),
            patch("devhub.cli.CACHE_DIR", tmp_path / "cache"),
        ):
            ensure_devhub_home()

            assert tmp_path.exists()
            assert (tmp_path / "vault").exists()
            assert (tmp_path / "cache").exists()

    def test_load_config_empty_case(self, tmp_path: Path) -> None:
        """Test loading config when no config files exist."""
        with (
            patch("devhub.cli.GLOBAL_CONFIG", tmp_path / "nonexistent.yaml"),
            patch("devhub.cli.Path.cwd", return_value=tmp_path),
        ):
            config = load_config()
            assert config == {}

    def test_load_config_global_only(self, tmp_path: Path) -> None:
        """Test loading config with only global config."""
        global_config = tmp_path / "global.yaml"
        global_config.write_text("global_key: global_value\n")

        with (
            patch("devhub.cli.GLOBAL_CONFIG", global_config),
            patch("devhub.cli.Path.cwd", return_value=tmp_path),
        ):
            config = load_config()
            assert config == {"global_key": "global_value"}

    def test_load_config_project_only(self, tmp_path: Path) -> None:
        """Test loading config with only project config."""
        project_config = tmp_path / ".devhub.yaml"
        project_config.write_text("project_key: project_value\n")

        with (
            patch("devhub.cli.GLOBAL_CONFIG", tmp_path / "nonexistent.yaml"),
            patch("devhub.cli.Path.cwd", return_value=tmp_path),
        ):
            config = load_config()
            assert config == {"project_key": "project_value"}

    def test_load_config_project_overrides_global(self, tmp_path: Path) -> None:
        """Test that project config overrides global config."""
        global_config = tmp_path / "global.yaml"
        global_config.write_text("shared_key: global_value\nglobal_only: global\n")

        project_config = tmp_path / ".devhub.yaml"
        project_config.write_text("shared_key: project_value\nproject_only: project\n")

        with (
            patch("devhub.cli.GLOBAL_CONFIG", global_config),
            patch("devhub.cli.Path.cwd", return_value=tmp_path),
        ):
            config = load_config()
            expected = {
                "shared_key": "project_value",  # Project overrides
                "global_only": "global",  # Global preserved
                "project_only": "project",  # Project added
            }
            assert config == expected

    def test_save_global_config(self, tmp_path: Path) -> None:
        """Test saving global configuration."""
        global_config = tmp_path / "config.yaml"
        test_config = {"test_key": "test_value", "nested": {"key": "value"}}

        with patch("devhub.cli.GLOBAL_CONFIG", global_config), patch("devhub.cli.ensure_devhub_home"):
            save_global_config(test_config)

            # Verify file was written
            assert global_config.exists()
            loaded = yaml.safe_load(global_config.read_text())
            assert loaded == test_config

    def test_detect_repository_platform_no_git(self, tmp_path: Path) -> None:
        """Test platform detection when no git repository exists."""
        with patch("devhub.cli.Path.cwd", return_value=tmp_path):
            platform, info = _detect_repository_platform()
            assert platform == "none"
            assert info == {}

    def test_detect_repository_platform_git_without_config(self, tmp_path: Path) -> None:
        """Test platform detection with git repo but no config."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        with patch("devhub.cli.Path.cwd", return_value=tmp_path):
            platform, info = _detect_repository_platform()
            assert platform == "git"
            assert info == {}

    def test_detect_repository_platform_git_with_config_error(self, tmp_path: Path) -> None:
        """Test platform detection when git config read fails."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        git_config = git_dir / "config"
        git_config.write_text("invalid content")

        with (
            patch("devhub.cli.Path.cwd", return_value=tmp_path),
            patch("builtins.open", side_effect=OSError("Permission denied")),
        ):
            platform, info = _detect_repository_platform()
            assert platform == "git"
            assert info == {}

    def test_parse_git_remote_info_github_ssh(self) -> None:
        """Test parsing GitHub SSH remote info."""
        content = """[remote "origin"]
    url = git@github.com:myorg/myrepo.git
    fetch = +refs/heads/*:refs/remotes/origin/*
"""
        platform, info = _parse_git_remote_info(content)
        assert platform == "github"
        assert info == {"organization": "myorg", "repository": "myrepo"}

    def test_parse_git_remote_info_github_https(self) -> None:
        """Test parsing GitHub HTTPS remote info."""
        content = """[remote "origin"]
    url = https://github.com/testorg/testrepo.git
    fetch = +refs/heads/*:refs/remotes/origin/*
"""
        platform, info = _parse_git_remote_info(content)
        assert platform == "github"
        assert info == {"organization": "testorg", "repository": "testrepo"}

    def test_parse_git_remote_info_gitlab_ssh(self) -> None:
        """Test parsing GitLab SSH remote info."""
        content = """[remote "origin"]
    url = git@gitlab.com:myorg/myrepo.git
    fetch = +refs/heads/*:refs/remotes/origin/*
"""
        platform, info = _parse_git_remote_info(content)
        assert platform == "gitlab"
        assert info == {"organization": "myorg", "repository": "myrepo"}

    def test_parse_git_remote_info_gitlab_no_match(self) -> None:
        """Test GitLab detection without organization match."""
        content = """[remote "origin"]
    url = https://some-gitlab-instance.com/path
    fetch = +refs/heads/*:refs/remotes/origin/*
"""
        platform, info = _parse_git_remote_info(content)
        assert platform == "gitlab"
        assert info == {"base_url": "https://gitlab.com"}

    def test_parse_git_remote_info_generic_git(self) -> None:
        """Test parsing non-GitHub/GitLab git remote."""
        content = """[remote "origin"]
    url = https://example.com/git/repo.git
    fetch = +refs/heads/*:refs/remotes/origin/*
"""
        platform, info = _parse_git_remote_info(content)
        assert platform == "git"
        assert info == {}

    def test_detect_project_type_empty_directory(self, tmp_path: Path) -> None:
        """Test project type detection in empty directory."""
        with patch("devhub.cli.Path.cwd", return_value=tmp_path):
            types = _detect_project_type()
            assert types == []

    def test_detect_project_type_nodejs(self, tmp_path: Path) -> None:
        """Test Node.js project detection."""
        (tmp_path / "package.json").write_text("{}")

        with patch("devhub.cli.Path.cwd", return_value=tmp_path):
            types = _detect_project_type()
            assert "Node.js" in types

    def test_detect_project_type_python_requirements(self, tmp_path: Path) -> None:
        """Test Python project detection via requirements.txt."""
        (tmp_path / "requirements.txt").write_text("requests==2.28.0\n")

        with patch("devhub.cli.Path.cwd", return_value=tmp_path):
            types = _detect_project_type()
            assert "Python" in types

    def test_detect_project_type_python_pyproject(self, tmp_path: Path) -> None:
        """Test Python project detection via pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text("[build-system]\n")

        with patch("devhub.cli.Path.cwd", return_value=tmp_path):
            types = _detect_project_type()
            assert "Python" in types

    def test_detect_project_type_rust(self, tmp_path: Path) -> None:
        """Test Rust project detection."""
        (tmp_path / "Cargo.toml").write_text("[package]\n")

        with patch("devhub.cli.Path.cwd", return_value=tmp_path):
            types = _detect_project_type()
            assert "Rust" in types

    def test_detect_project_type_go(self, tmp_path: Path) -> None:
        """Test Go project detection."""
        (tmp_path / "go.mod").write_text("module example.com/mymodule\n")

        with patch("devhub.cli.Path.cwd", return_value=tmp_path):
            types = _detect_project_type()
            assert "Go" in types

    def test_detect_project_type_java_maven(self, tmp_path: Path) -> None:
        """Test Java project detection via Maven."""
        (tmp_path / "pom.xml").write_text("<project></project>")

        with patch("devhub.cli.Path.cwd", return_value=tmp_path):
            types = _detect_project_type()
            assert "Java" in types

    def test_detect_project_type_java_gradle(self, tmp_path: Path) -> None:
        """Test Java project detection via Gradle."""
        (tmp_path / "build.gradle").write_text("apply plugin: 'java'\n")

        with patch("devhub.cli.Path.cwd", return_value=tmp_path):
            types = _detect_project_type()
            assert "Java" in types

    def test_detect_project_type_multiple(self, tmp_path: Path) -> None:
        """Test detection of multiple project types."""
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / "requirements.txt").write_text("requests==2.28.0\n")
        (tmp_path / "go.mod").write_text("module example.com/mymodule\n")

        with patch("devhub.cli.Path.cwd", return_value=tmp_path):
            types = _detect_project_type()
            assert set(types) == {"Node.js", "Python", "Go"}


class TestCLIInteractiveFunctions:
    """Test CLI interactive functions."""

    def test_get_user_choice_valid_first_option(self) -> None:
        """Test getting valid user choice - first option."""
        options = [("github", "GitHub"), ("gitlab", "GitLab"), ("none", "None")]

        with patch("click.prompt", return_value="1"):
            choice = _get_user_choice(options, "Choose platform")
            assert choice == "github"

    def test_get_user_choice_valid_last_option(self) -> None:
        """Test getting valid user choice - last option."""
        options = [("github", "GitHub"), ("gitlab", "GitLab"), ("none", "None")]

        with patch("click.prompt", return_value="3"):
            choice = _get_user_choice(options, "Choose platform")
            assert choice == "none"

    def test_get_user_choice_invalid_then_valid(self) -> None:
        """Test getting user choice with invalid input followed by valid."""
        options = [("github", "GitHub"), ("gitlab", "GitLab")]

        with (
            patch("click.prompt", side_effect=["invalid", "5", "1"]),
            patch("click.echo"),  # Suppress error messages
        ):
            choice = _get_user_choice(options, "Choose platform")
            assert choice == "github"

    def test_get_user_choice_out_of_range_then_valid(self) -> None:
        """Test getting user choice with out-of-range input."""
        options = [("github", "GitHub"), ("gitlab", "GitLab")]

        with patch("click.prompt", side_effect=["0", "5", "2"]), patch("click.echo"):  # Suppress error messages
            choice = _get_user_choice(options, "Choose platform")
            assert choice == "gitlab"

    def test_display_detection_results_github_with_info(self) -> None:
        """Test displaying GitHub detection results with organization info."""
        detected_info = {"organization": "myorg", "repository": "myrepo"}

        with patch("click.echo") as mock_echo:
            _display_detection_results("github", detected_info)

            # Verify the right messages were displayed
            calls = [call[0][0] for call in mock_echo.call_args_list]
            assert any("GitHub repository detected" in call for call in calls)
            assert any("Organization: myorg" in call for call in calls)
            assert any("Repository: myrepo" in call for call in calls)

    def test_display_detection_results_github_without_info(self) -> None:
        """Test displaying GitHub detection results without organization info."""
        with patch("click.echo") as mock_echo:
            _display_detection_results("github", {})

            calls = [call[0][0] for call in mock_echo.call_args_list]
            assert any("GitHub repository detected" in call for call in calls)
            # Should not have organization info
            assert not any("Organization:" in call for call in calls)

    def test_display_detection_results_gitlab_with_info(self) -> None:
        """Test displaying GitLab detection results with organization info."""
        detected_info = {"organization": "myorg"}

        with patch("click.echo") as mock_echo:
            _display_detection_results("gitlab", detected_info)

            calls = [call[0][0] for call in mock_echo.call_args_list]
            assert any("GitLab repository detected" in call for call in calls)
            assert any("Organization: myorg" in call for call in calls)

    def test_display_detection_results_git_only(self) -> None:
        """Test displaying git-only detection results."""
        with patch("click.echo") as mock_echo:
            _display_detection_results("git", {})

            calls = [call[0][0] for call in mock_echo.call_args_list]
            assert any("Git repository (platform unknown)" in call for call in calls)

    def test_display_detection_results_no_git(self) -> None:
        """Test displaying no-git detection results."""
        with patch("click.echo") as mock_echo:
            _display_detection_results("none", {})

            calls = [call[0][0] for call in mock_echo.call_args_list]
            assert any("No git repository found" in call for call in calls)

    def test_prompt_repository_platform_github_detected(self) -> None:
        """Test repository platform prompt with GitHub detected."""
        with patch("click.echo"), patch("devhub.cli._get_user_choice", return_value="github") as mock_choice:
            result = _prompt_repository_platform("github")

            assert result == "github"
            # Verify the options passed to _get_user_choice
            called_options = mock_choice.call_args[0][0]
            option_keys = [opt[0] for opt in called_options]
            assert option_keys == ["github", "gitlab", "none"]

    def test_prompt_project_management(self) -> None:
        """Test project management platform prompt."""
        with patch("click.echo"), patch("devhub.cli._get_user_choice", return_value="jira") as mock_choice:
            result = _prompt_project_management()

            assert result == "jira"
            # Verify the options passed to _get_user_choice
            called_options = mock_choice.call_args[0][0]
            option_keys = [opt[0] for opt in called_options]
            assert option_keys == ["jira", "github", "gitlab", "none"]


class TestConfigCreation:
    """Test configuration creation functions."""

    def test_create_config_from_flags_github_only(self) -> None:
        """Test creating config from GitHub flag only."""
        with patch("click.prompt", return_value="testorg"):
            config = _create_config_from_flags(github=True, gitlab=False, jira=False, github_projects=False)

            assert config["version"] == "1.0"
            assert config["platforms"]["repository"] == "github"
            assert config["platforms"]["project_management"] == "none"
            assert config["github"]["enabled"] is True
            assert config["github"]["organization"] == "testorg"
            assert config["github"]["projects"] is False
            assert config["gitlab"]["enabled"] is False
            assert config["jira"]["enabled"] is False

    def test_create_config_from_flags_github_with_projects(self) -> None:
        """Test creating config with GitHub and GitHub Projects."""
        with patch("click.prompt", return_value="testorg"):
            config = _create_config_from_flags(github=True, gitlab=False, jira=False, github_projects=True)

            assert config["platforms"]["repository"] == "github"
            assert config["platforms"]["project_management"] == "github"
            assert config["github"]["projects"] is True

    def test_create_config_from_flags_gitlab_only(self) -> None:
        """Test creating config from GitLab flag only."""
        with patch("click.prompt", return_value="https://custom-gitlab.com"):
            config = _create_config_from_flags(github=False, gitlab=True, jira=False, github_projects=False)

            assert config["platforms"]["repository"] == "gitlab"
            assert config["platforms"]["project_management"] == "none"
            assert config["gitlab"]["enabled"] is True
            assert config["gitlab"]["base_url"] == "https://custom-gitlab.com"
            assert config["github"]["enabled"] is False
            assert config["jira"]["enabled"] is False

    def test_create_config_from_flags_jira_only(self) -> None:
        """Test creating config from Jira flag only."""
        with patch("click.prompt", side_effect=["https://company.atlassian.net", "PROJ"]):
            config = _create_config_from_flags(github=False, gitlab=False, jira=True, github_projects=False)

            assert config["platforms"]["repository"] == "none"
            assert config["platforms"]["project_management"] == "jira"
            assert config["jira"]["enabled"] is True
            assert config["jira"]["base_url"] == "https://company.atlassian.net"
            assert config["jira"]["project_key"] == "PROJ"
            assert config["github"]["enabled"] is False
            assert config["gitlab"]["enabled"] is False

    def test_create_config_from_flags_all_disabled(self) -> None:
        """Test creating config with all flags disabled."""
        config = _create_config_from_flags(github=False, gitlab=False, jira=False, github_projects=False)

        assert config["platforms"]["repository"] == "none"
        assert config["platforms"]["project_management"] == "none"
        assert config["github"]["enabled"] is False
        assert config["gitlab"]["enabled"] is False
        assert config["jira"]["enabled"] is False
        assert "bundle" in config

    def test_load_profile_config_exists(self, tmp_path: Path) -> None:
        """Test loading profile config when profile exists."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        profile_file = profiles_dir / "myprofile.yaml"
        profile_config = {"version": "1.0", "profile": "custom"}
        profile_file.write_text(yaml.dump(profile_config))

        with patch("devhub.cli.DEVHUB_HOME", tmp_path):
            config = _load_profile_config("myprofile")
            assert config == profile_config

    def test_load_profile_config_not_exists(self, tmp_path: Path) -> None:
        """Test loading profile config when profile doesn't exist."""
        with (
            patch("devhub.cli.DEVHUB_HOME", tmp_path),
            pytest.raises(SystemExit),  # Profile loading fails with SystemExit
        ):
            _load_profile_config("nonexistent")

    def test_create_project_config_with_profile(self) -> None:
        """Test creating project config using a profile."""
        expected_config = {"version": "1.0", "from_profile": True}

        with patch("devhub.cli._load_profile_config", return_value=expected_config):
            config = _create_project_config(
                github=False, gitlab=False, jira=False, github_projects=False, profile="myprofile"
            )
            assert config == expected_config

    def test_create_project_config_with_flags(self) -> None:
        """Test creating project config using flags."""
        with patch("devhub.cli._create_config_from_flags") as mock_create:
            mock_create.return_value = {"from_flags": True}

            config = _create_project_config(github=True, gitlab=False, jira=False, github_projects=False, profile=None)

            assert config == {"from_flags": True}
            mock_create.assert_called_once_with(github=True, gitlab=False, jira=False, github_projects=False)

    @patch("devhub.cli._prompt_platform_selection")
    @patch("devhub.cli._detect_repository_platform")
    def test_create_project_config_interactive_github(self, mock_detect: Mock, mock_prompt: Mock) -> None:
        """Test creating project config interactively with GitHub selection."""
        # Mock detection and user selection
        mock_detect.return_value = ("github", {"organization": "testorg", "repository": "testrepo"})
        mock_prompt.return_value = {
            "repository": "github",
            "project_management": "jira",
        }

        with patch("click.prompt", side_effect=["", "https://company.atlassian.net", "PROJ"]):
            config = _create_project_config(github=False, gitlab=False, jira=False, github_projects=False, profile=None)

            assert config["version"] == "1.0"
            assert config["platforms"]["repository"] == "github"
            assert config["platforms"]["project_management"] == "jira"
            assert config["github"]["enabled"] is True
            assert config["github"]["organization"] == "testorg"  # From detected info
            assert config["gitlab"]["enabled"] is False
            assert config["jira"]["enabled"] is True

    @patch("devhub.cli._prompt_platform_selection")
    @patch("devhub.cli._detect_repository_platform")
    def test_create_project_config_interactive_gitlab(self, mock_detect: Mock, mock_prompt: Mock) -> None:
        """Test creating project config interactively with GitLab selection."""
        mock_detect.return_value = ("gitlab", {"base_url": "https://custom-gitlab.com"})
        mock_prompt.return_value = {
            "repository": "gitlab",
            "project_management": "none",
        }

        with patch("click.prompt", return_value="https://custom-gitlab.com"):
            config = _create_project_config(github=False, gitlab=False, jira=False, github_projects=False, profile=None)

            assert config["platforms"]["repository"] == "gitlab"
            assert config["platforms"]["project_management"] == "none"
            assert config["gitlab"]["enabled"] is True
            assert config["gitlab"]["base_url"] == "https://custom-gitlab.com"
            assert config["github"]["enabled"] is False
            assert config["jira"]["enabled"] is False

    @patch("devhub.cli._prompt_platform_selection")
    @patch("devhub.cli._detect_repository_platform")
    def test_create_project_config_interactive_none(self, mock_detect: Mock, mock_prompt: Mock) -> None:
        """Test creating project config interactively with no platforms."""
        mock_detect.return_value = ("none", {})
        mock_prompt.return_value = {
            "repository": "none",
            "project_management": "none",
        }

        config = _create_project_config(github=False, gitlab=False, jira=False, github_projects=False, profile=None)

        assert config["platforms"]["repository"] == "none"
        assert config["platforms"]["project_management"] == "none"
        assert config["github"]["enabled"] is False
        assert config["gitlab"]["enabled"] is False
        assert config["jira"]["enabled"] is False

    @patch("devhub.cli._display_detection_results")
    @patch("devhub.cli._prompt_repository_platform")
    @patch("devhub.cli._prompt_project_management")
    def test_prompt_platform_selection(self, mock_pm: Mock, mock_repo: Mock, mock_display: Mock) -> None:
        """Test the complete platform selection flow."""
        mock_repo.return_value = "github"
        mock_pm.return_value = "jira"
        detected_info = {"organization": "testorg"}

        result = _prompt_platform_selection("github", detected_info)

        expected = {
            "repository": "github",
            "project_management": "jira",
            "detected_info": detected_info,
        }
        assert result == expected
        mock_display.assert_called_once_with("github", detected_info)


class TestCLICommands:
    """Test CLI commands that weren't covered in integration tests."""

    @pytest.fixture
    def cli_runner(self) -> CliRunner:
        """Provide a Click CLI test runner."""
        return CliRunner()

    def test_cli_main_group_help(self, cli_runner: CliRunner) -> None:
        """Test main CLI group help."""
        result = cli_runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "DevHub - Transform Claude Code" in result.output
        assert "Commands:" in result.output

    def test_cli_version_flag(self, cli_runner: CliRunner) -> None:
        """Test CLI version flag."""
        result = cli_runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    @patch("devhub.cli.load_config")
    def test_config_show_command_with_config(self, mock_load: Mock, cli_runner: CliRunner) -> None:
        """Test config show command with existing config."""
        mock_config = {"jira": {"base_url": "https://test.atlassian.net"}, "github": {"organization": "testorg"}}
        mock_load.return_value = mock_config

        result = cli_runner.invoke(cli, ["config", "show"])
        assert result.exit_code == 0
        # The config show command outputs YAML format
        assert "jira:" in result.output
        assert "github:" in result.output

    @patch("devhub.cli.load_config")
    def test_config_show_command_empty_config(self, mock_load: Mock, cli_runner: CliRunner) -> None:
        """Test config show command with empty config."""
        mock_load.return_value = {}

        result = cli_runner.invoke(cli, ["config", "show"])
        assert result.exit_code == 0
        # Empty config shows as {}
        assert "{}" in result.output

    def test_init_command_help(self, cli_runner: CliRunner) -> None:
        """Test init command help."""
        result = cli_runner.invoke(cli, ["init", "--help"])
        assert result.exit_code == 0
        assert "Initialize DevHub for this project" in result.output

    def test_auth_command_help(self, cli_runner: CliRunner) -> None:
        """Test auth command help."""
        result = cli_runner.invoke(cli, ["auth", "--help"])
        assert result.exit_code == 0
        assert "Manage authentication and credentials" in result.output

    def test_claude_command_help(self, cli_runner: CliRunner) -> None:
        """Test claude command help."""
        result = cli_runner.invoke(cli, ["claude", "--help"])
        assert result.exit_code == 0
        assert "Claude Code integration commands" in result.output
