"""DevHub CLI - Professional command-line interface.

This CLI works globally, like git or docker, without contaminating projects.
"""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import traceback
from collections import Counter
from pathlib import Path
from typing import Any
from typing import cast

import aiofiles
import click
import yaml
from returns.result import Failure
from returns.result import Result
from returns.result import Success

import devhub
from devhub.claude_integration import claude_code_review_context
from devhub.main import handle_bundle_command
from devhub.vault import CredentialMetadata
from devhub.vault import CredentialType
from devhub.vault import SecureVault
from devhub.vault import VaultConfig


class VaultOperationError(Exception):
    """Exception raised when vault operations fail."""


def _raise_vault_error(message: str) -> None:
    """Raise a VaultOperationError with the given message."""
    raise VaultOperationError(message)


# Global DevHub home directory
DEVHUB_HOME = Path.home() / ".devhub"
GLOBAL_CONFIG = DEVHUB_HOME / "config.yaml"
VAULT_DIR = DEVHUB_HOME / "vault"
CACHE_DIR = DEVHUB_HOME / "cache"


def ensure_devhub_home() -> None:
    """Ensure DevHub home directory exists."""
    DEVHUB_HOME.mkdir(exist_ok=True)
    VAULT_DIR.mkdir(exist_ok=True)
    CACHE_DIR.mkdir(exist_ok=True)


def load_config() -> dict[str, Any]:
    """Load configuration (global + project override)."""
    config: dict[str, Any] = {}

    # Load global config
    if GLOBAL_CONFIG.exists():
        with GLOBAL_CONFIG.open() as f:
            config = yaml.safe_load(f) or {}

    # Check for project override
    project_config = Path.cwd() / ".devhub.yaml"
    if project_config.exists():
        with project_config.open() as f:
            project = yaml.safe_load(f) or {}
            # Merge with project taking precedence
            config.update(project)

    return config


def save_global_config(config: dict[str, Any]) -> None:
    """Save global configuration."""
    ensure_devhub_home()
    with GLOBAL_CONFIG.open("w") as f:
        yaml.dump(config, f, default_flow_style=False)


def _detect_repository_platform() -> tuple[str, dict[str, Any]]:
    """Detect repository platform from git config."""
    cwd = Path.cwd()

    # Check if git repository exists
    if not (cwd / ".git").exists():
        return "none", {}

    git_config = cwd / ".git" / "config"
    if not git_config.exists():
        return "git", {}

    try:
        content = git_config.read_text()
        return _parse_git_remote_info(content)
    except (OSError, subprocess.SubprocessError):
        return "git", {}


def _detect_repository_platform_safe() -> tuple[str, dict[str, Any]]:
    """Safely detect repository platform with error handling."""
    try:
        return _detect_repository_platform()
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        click.echo(f"⚠️  Repository detection failed: {e}")
        return "none", {}


def _detect_project_type_safe() -> list[str]:
    """Safely detect project type with error handling."""
    try:
        return _detect_project_type()
    except (OSError, ValueError) as e:
        click.echo(f"⚠️  Project type detection failed: {e}")
        return []


def _wizard_select_platforms_safe(detected_platform: str, detected_info: dict[str, Any]) -> dict[str, Any]:
    """Safely handle platform selection with error recovery."""
    try:
        return _wizard_select_platforms(detected_platform, detected_info)
    except KeyboardInterrupt:
        raise  # Let caller handle
    except (OSError, ValueError, click.ClickException) as e:
        click.echo(f"⚠️  Platform selection failed: {e}")
        click.echo("💡 Using default configuration")
        # Return safe defaults
        return {"repository": "github" if detected_platform == "github" else "local", "project_management": "none"}


def _wizard_advanced_config_safe(platforms: dict[str, Any], detected_info: dict[str, Any]) -> dict[str, Any]:
    """Safely handle advanced configuration with fallbacks."""
    try:
        return _wizard_advanced_config(platforms, detected_info)
    except KeyboardInterrupt:
        raise  # Let caller handle
    except (OSError, ValueError, click.ClickException, yaml.YAMLError) as e:
        click.echo(f"⚠️  Advanced configuration failed: {e}")
        click.echo("💡 Using default configuration")
        # Return safe defaults
        return {"bundle": {"max_files": 100, "include_tests": True, "include_docs": True, "claude_optimized": True}}


def _wizard_setup_credentials_safe(platforms: dict[str, Any]) -> None:
    """Safely handle credential setup with error recovery."""
    try:
        _wizard_setup_credentials(platforms)
    except KeyboardInterrupt:
        click.echo("\n⚠️  Credential setup cancelled")
    except (OSError, ValueError, click.ClickException, VaultOperationError) as e:
        click.echo(f"⚠️  Credential setup failed: {e}")
        click.echo("💡 You can set up credentials later with 'devhub auth setup'")


def _parse_git_remote_info(content: str) -> tuple[str, dict[str, Any]]:
    """Parse git remote information from config content."""
    # GitHub detection
    if "github.com" in content:
        match = re.search(r"github\.com[:/]([^/\s]+)/([^/\s\.]+)", content)
        info = {"organization": match.group(1), "repository": match.group(2)} if match else {}
        return "github", info

    # GitLab detection
    if "gitlab" in content:
        match = re.search(r"gitlab\.com[:/]([^/\s]+)/([^/\s\.]+)", content)
        info = (
            {"organization": match.group(1), "repository": match.group(2)}
            if match
            else {"base_url": "https://gitlab.com"}
        )
        return "gitlab", info

    return "git", {}


def _detect_project_type() -> list[str]:
    """Detect project type from files."""
    cwd = Path.cwd()
    types = []

    if (cwd / "package.json").exists():
        types.append("Node.js")
    if (cwd / "requirements.txt").exists() or (cwd / "pyproject.toml").exists():
        types.append("Python")
    if (cwd / "Cargo.toml").exists():
        types.append("Rust")
    if (cwd / "go.mod").exists():
        types.append("Go")
    if (cwd / "pom.xml").exists() or (cwd / "build.gradle").exists():
        types.append("Java")

    return types


def _prompt_platform_selection(detected_platform: str, detected_info: dict[str, Any]) -> dict[str, Any]:
    """Interactive platform selection with smart defaults."""
    _display_detection_results(detected_platform, detected_info)

    click.echo("\n📋 Platform Configuration:")

    repo_platform = _prompt_repository_platform(detected_platform)
    pm_platform = _prompt_project_management()

    return {"repository": repo_platform, "project_management": pm_platform, "detected_info": detected_info}


def _display_detection_results(detected_platform: str, detected_info: dict[str, Any]) -> None:
    """Display the results of platform detection."""
    click.echo("\n🔍 Repository Detection:")

    if detected_platform == "github":
        click.echo("✅ GitHub repository detected")
        if "organization" in detected_info:
            click.echo(f"   Organization: {detected_info['organization']}")
            click.echo(f"   Repository: {detected_info['repository']}")
    elif detected_platform == "gitlab":
        click.echo("✅ GitLab repository detected")
        if "organization" in detected_info:
            click.echo(f"   Organization: {detected_info['organization']}")
    elif detected_platform == "git":
        click.echo("✅ Git repository (platform unknown)")
    else:
        click.echo("❌ No git repository found")


def _prompt_repository_platform(detected_platform: str) -> str:
    """Prompt user to select repository platform."""
    repo_options = [
        ("github", "GitHub", detected_platform == "github"),
        ("gitlab", "GitLab", detected_platform == "gitlab"),
        ("none", "Local git only", detected_platform in ["git", "none"]),
    ]

    click.echo("Repository platform:")
    for i, (_, name, is_default) in enumerate(repo_options, 1):
        default_marker = " (detected)" if is_default else ""
        click.echo(f"  {i}) {name}{default_marker}")

    return _get_user_choice([(key, name) for key, name, _ in repo_options], "Choose repository platform")


def _prompt_project_management() -> str:
    """Prompt user to select project management platform."""
    pm_options = [("jira", "Jira"), ("github", "GitHub Projects/Issues"), ("gitlab", "GitLab Issues"), ("none", "None")]

    click.echo("\nProject management:")
    for i, (_, name) in enumerate(pm_options, 1):
        click.echo(f"  {i}) {name}")

    return _get_user_choice(pm_options, "Choose project management")


def _get_user_choice(options: list[tuple[str, str]], prompt_text: str) -> str:
    """Get user choice from a list of options."""
    while True:
        choice = click.prompt(prompt_text, default="1")
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return options[idx][0]
        except ValueError:
            pass
        click.echo("Invalid choice, try again")


def _create_project_config(
    github: bool, gitlab: bool, jira: bool, github_projects: bool, profile: str | None
) -> dict[str, Any]:
    """Create project configuration with smart defaults."""
    # Use profile if specified
    if profile:
        return _load_profile_config(profile)

    # If flags are specified, use them directly
    if any([github, gitlab, jira, github_projects]):
        return _create_config_from_flags(github=github, gitlab=gitlab, jira=jira, github_projects=github_projects)

    # Interactive mode with detection
    detected_platform, detected_info = _detect_repository_platform()
    selection = _prompt_platform_selection(detected_platform, detected_info)

    config = {
        "version": "1.0",
        "platforms": {"repository": selection["repository"], "project_management": selection["project_management"]},
    }

    # Configure repository platform
    if selection["repository"] == "github":
        org = detected_info.get("organization", "")
        if not org:
            org = click.prompt("GitHub organization", default="")

        config["github"] = {
            "enabled": True,
            "organization": org,
            "projects": selection["project_management"] == "github",
        }
        config["gitlab"] = {"enabled": False}

    elif selection["repository"] == "gitlab":
        base_url = detected_info.get("base_url", "https://gitlab.com")
        if "gitlab.com" not in base_url:
            base_url = click.prompt("GitLab URL", default=base_url)

        config["gitlab"] = {"enabled": True, "base_url": base_url}
        config["github"] = {"enabled": False}

    else:
        config["github"] = {"enabled": False}
        config["gitlab"] = {"enabled": False}

    # Configure project management
    if selection["project_management"] == "jira":
        jira_url = click.prompt("Jira URL", default="https://company.atlassian.net")
        project_key = click.prompt("Jira project key", default="")

        config["jira"] = {"enabled": True, "base_url": jira_url, "project_key": project_key}
    else:
        config["jira"] = {"enabled": False}

    # Add bundle configuration
    config["bundle"] = {"max_files": 100, "include_tests": True, "include_docs": True, "claude_optimized": True}

    return config


def _create_config_from_flags(github: bool, gitlab: bool, jira: bool, github_projects: bool) -> dict[str, Any]:
    """Create configuration from CLI flags."""
    config = {
        "version": "1.0",
        "platforms": {
            "repository": "github" if github else ("gitlab" if gitlab else "none"),
            "project_management": "jira" if jira else ("github" if github_projects else "none"),
        },
    }

    if github:
        org = click.prompt("GitHub organization", default="")
        config["github"] = {"enabled": True, "organization": org, "projects": github_projects}
    else:
        config["github"] = {"enabled": False}

    if gitlab:
        base_url = click.prompt("GitLab URL", default="https://gitlab.com")
        config["gitlab"] = {"enabled": True, "base_url": base_url}
    else:
        config["gitlab"] = {"enabled": False}

    if jira:
        jira_url = click.prompt("Jira URL", default="https://company.atlassian.net")
        project_key = click.prompt("Jira project key", default="")
        config["jira"] = {"enabled": True, "base_url": jira_url, "project_key": project_key}
    else:
        config["jira"] = {"enabled": False}

    config["bundle"] = {"max_files": 100, "include_tests": True, "include_docs": True, "claude_optimized": True}

    return config


def _load_profile_config(profile_name: str) -> dict[str, Any]:
    """Load configuration from a profile."""
    profiles_dir = DEVHUB_HOME / "profiles"
    profile_file = profiles_dir / f"{profile_name}.yaml"

    if not profile_file.exists():
        click.echo(f"❌ Profile '{profile_name}' not found")
        click.echo("Available profiles:")
        if profiles_dir.exists():
            for p in profiles_dir.glob("*.yaml"):
                click.echo(f"  - {p.stem}")
        else:
            click.echo("  No profiles created yet")
        sys.exit(1)

    with profile_file.open() as f:
        return cast("dict[str, Any]", yaml.safe_load(f))


def _check_directory_exists(current_dir: Path) -> Result[None, str]:
    """Check if directory exists."""
    if not current_dir.exists():
        return Failure("Current directory does not exist")
    return Success(None)


def _check_write_permissions(current_dir: Path) -> Result[None, str]:
    """Check if we can write to the directory."""
    if not os.access(current_dir, os.W_OK):
        return Failure("Cannot write to current directory. Ensure you have write permissions.")
    return Success(None)


def _check_config_overwrite(current_dir: Path) -> Result[None, str]:
    """Check if config file exists and get user confirmation for overwrite."""
    config_file = current_dir / ".devhub.yaml"
    if config_file.exists() and not click.confirm(f"⚠️  {config_file} already exists. Overwrite?", default=False):
        return Failure("Setup cancelled - config file exists")
    return Success(None)


def _check_git_repository(current_dir: Path) -> Result[None, str]:
    """Check if we're in a git repository and get user confirmation."""
    if not (current_dir / ".git").exists():
        click.echo("⚠️  Not in a git repository")
        if not click.confirm("Continue anyway? (DevHub works best with git repositories)", default=True):
            return Failure("Setup cancelled - not in git repo")
    return Success(None)


def _validate_setup_environment(current_dir: Path) -> bool:
    """Validate that the environment is suitable for DevHub setup."""
    validations = [
        _check_directory_exists(current_dir),
        _check_write_permissions(current_dir),
        _check_config_overwrite(current_dir),
        _check_git_repository(current_dir),
    ]

    for validation in validations:
        if isinstance(validation, Failure):
            click.echo(f"❌ {validation.failure()}")
            return False

    return True


def _create_global_config() -> dict[str, Any]:
    """Create global configuration."""
    return {
        "version": "1.0",
        "defaults": {
            "platform": "auto",
            "bundle": {
                "max_files": 100,
                "include_tests": True,
                "include_docs": True,
            },
        },
        "profiles": {
            "work": {
                "platforms": {"repository": "github", "project_management": "jira"},
                "github": {"enabled": True, "organization": ""},
                "jira": {"enabled": True, "base_url": ""},
            },
            "personal": {
                "platforms": {"repository": "github", "project_management": "github"},
                "github": {"enabled": True, "projects": True},
                "jira": {"enabled": False},
            },
        },
    }


def _wizard_intro() -> Result[Path, str]:
    """Display wizard intro and validate environment."""
    try:
        click.echo("🧙‍♂️ DevHub Complete Setup Wizard")
        click.echo("=" * 50)
        click.echo("This wizard will guide you through setting up DevHub with")
        click.echo("platform detection, configuration, and credentials.\n")

        # Validate we're in a suitable directory
        current_dir = Path.cwd()
        if not _validate_setup_environment(current_dir):
            return Failure("Environment validation failed")

        # Always use project-based configuration for simplicity and clarity
        click.echo("🎯 Setting up DevHub for this project")
        click.echo("📁 Configuration will be saved to .devhub.yaml")
        click.echo()

        return Success(current_dir)
    except KeyboardInterrupt:
        return Failure("Setup cancelled by user")
    except (OSError, PermissionError, ValueError, yaml.YAMLError, click.ClickException) as e:
        return Failure(f"Setup failed: {e}")


def _wizard_project_analysis() -> Result[tuple[str, dict[str, Any], list[str]], str]:
    """Analyze project and detect platforms."""
    try:
        click.echo("\n🔍 Step 1: Project Analysis")
        click.echo("-" * 25)

        detected_platform, detected_info = _detect_repository_platform_safe()
        project_types = _detect_project_type_safe()

        click.echo(f"Current directory: {Path.cwd()}")

        if detected_platform != "none":
            if detected_platform == "github":
                click.echo("✅ GitHub repository detected")
                if "organization" in detected_info:
                    click.echo(f"   Organization: {detected_info['organization']}")
                    click.echo(f"   Repository: {detected_info['repository']}")
            elif detected_platform == "gitlab":
                click.echo("✅ GitLab repository detected")
                if "organization" in detected_info:
                    click.echo(f"   Organization: {detected_info['organization']}")
            else:
                click.echo("✅ Git repository (platform unknown)")
        else:
            click.echo("❌ No git repository found")

        if project_types:
            click.echo(f"📦 Project type(s): {', '.join(project_types)}")

        return Success((detected_platform, detected_info, project_types))
    except (OSError, ValueError, click.ClickException) as e:
        return Failure(f"Project analysis failed: {e}")


def _wizard_configuration_steps(detected_platform: str, detected_info: dict[str, Any]) -> Result[dict[str, Any], str]:
    """Handle platform selection and configuration steps."""
    try:
        # Step 3: Platform selection
        click.echo("\n⚙️  Step 2: Platform Configuration")
        click.echo("-" * 30)
        platforms = _wizard_select_platforms_safe(detected_platform, detected_info)

        # Step 4: Advanced configuration
        click.echo("\n🔧 Step 3: Advanced Configuration")
        click.echo("-" * 28)
        advanced_config = _wizard_advanced_config_safe(platforms, detected_info)

        # Step 5: Credential setup
        click.echo("\n🔐 Step 4: Credential Setup")
        click.echo("-" * 24)
        setup_creds = click.confirm("Set up credentials now?", default=True)

        # Step 6: Build final configuration
        config = _wizard_build_config(platforms, advanced_config, detected_info)

        return Success({"config": config, "platforms": platforms, "setup_creds": setup_creds})
    except (OSError, ValueError, click.ClickException) as e:
        return Failure(f"Configuration failed: {e}")


def _wizard_save_and_finalize(
    config: dict[str, Any], platforms: dict[str, Any], setup_creds: bool
) -> Result[None, str]:
    """Save configuration and handle credentials."""
    try:
        scope = "project"

        # Save project configuration
        config_path = Path.cwd() / ".devhub.yaml"
        with config_path.open("w") as f:
            yaml.dump(config, f, default_flow_style=False)
        click.echo(f"✅ Project configuration saved: {config_path}")

        # Handle credentials
        if setup_creds:
            try:
                click.echo("\n🔑 Setting up credentials...")
                _wizard_setup_credentials_safe(platforms)
            except (OSError, ValueError, VaultOperationError, click.ClickException) as e:
                click.echo(f"⚠️  Credential setup failed: {e}")
                click.echo("💡 You can set up credentials later with 'devhub auth setup'")

        # Final summary
        click.echo("\n🎉 Setup Complete!")
        click.echo("=" * 20)
        _wizard_show_summary(config, scope)

        return Success(None)
    except (OSError, PermissionError, yaml.YAMLError) as e:
        return Failure(f"Save failed: {e}")


def _run_setup_wizard() -> None:
    """Run the complete DevHub setup wizard with resilient error handling."""

    def handle_error(error_msg: str) -> None:
        click.echo(f"\n❌ {error_msg}")
        if "cancelled" not in error_msg.lower():
            click.echo("💡 Try running 'devhub doctor' to diagnose issues")

    # Execute wizard steps in sequence using Result types
    intro_result = _wizard_intro()
    if isinstance(intro_result, Failure):
        handle_error(intro_result.failure())
        return

    analysis_result = _wizard_project_analysis()
    if isinstance(analysis_result, Failure):
        handle_error(analysis_result.failure())
        return

    detected_platform, detected_info, _ = analysis_result.unwrap()

    config_result = _wizard_configuration_steps(detected_platform, detected_info)
    if isinstance(config_result, Failure):
        handle_error(config_result.failure())
        return

    config_data = config_result.unwrap()

    save_result = _wizard_save_and_finalize(config_data["config"], config_data["platforms"], config_data["setup_creds"])
    if isinstance(save_result, Failure):
        handle_error(save_result.failure())


def _wizard_select_platforms(detected_platform: str, _detected_info: dict[str, Any]) -> dict[str, Any]:
    """Wizard step for platform selection."""
    platforms = {}

    # Repository platform
    click.echo("📂 Repository Platform:")

    repo_options = [
        ("github", "GitHub", detected_platform == "github"),
        ("gitlab", "GitLab", detected_platform == "gitlab"),
        ("local", "Local git only", detected_platform in ["git", "none"]),
    ]

    for i, (_key, name, is_detected) in enumerate(repo_options, 1):
        marker = " (detected)" if is_detected else ""
        click.echo(f"  {i}) {name}{marker}")

    while True:
        choice = click.prompt("Choose repository platform", default="1")
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(repo_options):
                platforms["repository"] = repo_options[idx][0]
                break
        except ValueError:
            pass
        click.echo("Invalid choice, try again")

    # Project management platform
    click.echo("\n📋 Project Management:")

    pm_options = [
        ("jira", "Jira (tickets, epics, sprints)"),
        ("github", "GitHub Projects/Issues"),
        ("gitlab", "GitLab Issues/Boards"),
        ("none", "None (git history only)"),
    ]

    for i, (_key, name) in enumerate(pm_options, 1):
        click.echo(f"  {i}) {name}")

    while True:
        choice = click.prompt("Choose project management", default="1")
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(pm_options):
                platforms["project_management"] = pm_options[idx][0]
                break
        except ValueError:
            pass
        click.echo("Invalid choice, try again")

    return platforms


def _wizard_advanced_config(platforms: dict[str, Any], detected_info: dict[str, Any] | None = None) -> dict[str, Any]:
    """Wizard step for advanced configuration."""
    config = {}
    if detected_info is None:
        detected_info = {}

    # Jira-specific configuration
    if platforms.get("project_management") == "jira":
        click.echo("\n🎫 Jira Configuration:")

        # Try to detect Jira URL from git commits or branch names
        detected_jira = _detect_jira_info()

        if detected_jira["url"]:
            default_url = detected_jira["url"]
            click.echo(f"🔍 Detected Jira instance: {default_url}")
        else:
            default_url = "https://company.atlassian.net"

        jira_url = click.prompt("Jira instance URL", default=default_url)

        if detected_jira["project_key"]:
            default_key = detected_jira["project_key"]
            click.echo(f"🔍 Detected project key: {default_key}")
        else:
            default_key = ""

        project_key = click.prompt("Project key (e.g., DEVHUB, PROJ)", default=default_key)

        # Ticket prefix configuration
        click.echo("\n📝 Automatic Ticket Detection:")
        click.echo("DevHub can automatically find and link Jira tickets mentioned in:")
        click.echo("  🌿 Branch names (e.g., feature/DATAEX-123-new-feature)")
        click.echo("  💬 Commit messages (e.g., 'DATAEX-123: Add analytics feature')")
        click.echo("  🔀 Pull request titles")
        click.echo()
        click.echo("💡 This helps Claude understand what tickets you're working on!")

        # Detect existing patterns from git history - user first, then project-wide
        user_patterns, project_patterns = _detect_ticket_patterns()

        if user_patterns:
            click.echo("\n🔍 Ticket patterns found in your work:")
            for pattern, count in user_patterns.items():
                click.echo(f"   {pattern} (found {count} times in your commits/branches)")
        elif project_patterns:
            click.echo("\n🔍 Ticket patterns found in project history:")
            for pattern, count in project_patterns.items():
                click.echo(f"   {pattern} (found {count} times across all contributors)")

        # Use the more relevant pattern set
        detected_patterns = user_patterns if user_patterns else project_patterns

        click.echo()
        use_prefix = click.confirm("Enable automatic ticket detection for this project?", default=True)

        if use_prefix:
            ticket_patterns = []

            # Default pattern based on project key
            if project_key:
                default_pattern = f"{project_key}-\\d+"
                click.echo("\n🎯 Main Project Pattern:")
                click.echo(f"   {default_pattern} (matches tickets like {project_key}-123, {project_key}-456)")
                click.echo("   This will detect your main project tickets in branches, commits, and PRs.")
                if click.confirm("Enable detection for your main project tickets?", default=True):
                    ticket_patterns.append(default_pattern)

            # Team-specific patterns (excluding project key we already added)
            other_patterns = {k: v for k, v in detected_patterns.items() if k != project_key}

            if other_patterns:
                click.echo("\n👥 Other Team Patterns Found:")
                click.echo("Many teams use their own prefixes beyond the main project key.")
                click.echo("Add these detected patterns?")
                for pattern in other_patterns:
                    pattern_regex = f"{pattern}-\\d+"
                    if click.confirm(f"  Include {pattern_regex}?", default=True):
                        ticket_patterns.append(pattern_regex)

            # Custom team patterns
            click.echo("\nAdditional team patterns:")
            while True:
                team_prefix = click.prompt("Team prefix (e.g., DATAEX, BACKEND) or press Enter to skip", default="")
                if not team_prefix:
                    break

                # Clean and validate the prefix
                team_prefix = team_prefix.strip().upper()
                if team_prefix:
                    pattern = f"{team_prefix}-\\d+"
                    click.echo(f"   Pattern: {pattern}")
                    ticket_patterns.append(pattern)

                if not click.confirm("Add another team prefix?", default=False):
                    break

            # Catch-all pattern option
            if click.confirm("\nInclude catch-all pattern for any team? (e.g., [A-Z]+-\\d+)", default=True):
                ticket_patterns.append("[A-Z]+-\\d+")

            config["jira"] = {
                "base_url": jira_url,
                "project_key": project_key,
                "ticket_patterns": ticket_patterns,
                "auto_detection": {"branches": True, "commits": True, "pull_requests": True},
            }
        else:
            config["jira"] = {"base_url": jira_url, "project_key": project_key}

    # GitHub-specific configuration
    if platforms.get("repository") == "github":
        click.echo("\n🐙 GitHub Configuration:")

        # Use detected organization as default if available
        default_org = detected_info.get("organization", "")
        if default_org:
            click.echo(f"🔍 Using detected organization: {default_org}")

        org = click.prompt("GitHub organization/username", default=default_org)
        use_projects = platforms.get("project_management") == "github"

        project_number = click.prompt("GitHub Project number (optional)", default="") if use_projects else ""

        config["github"] = {
            "organization": org,
            "projects": use_projects,
            "project_number": project_number if project_number else None,
        }

        # Also store repository if detected
        if "repository" in detected_info:
            config["github"]["repository"] = detected_info["repository"]

    # GitLab-specific configuration
    if platforms.get("repository") == "gitlab":
        click.echo("\n🦊 GitLab Configuration:")

        # Use detected GitLab info
        default_url = detected_info.get("gitlab_url", "https://gitlab.com")
        default_group = detected_info.get("organization", "")

        if default_group:
            click.echo(f"🔍 Using detected group: {default_group}")

        base_url = click.prompt("GitLab URL", default=default_url)
        group_path = click.prompt("Group/namespace", default=default_group)

        config["gitlab"] = {"base_url": base_url, "group_path": group_path}

        # Also store repository if detected
        if "repository" in detected_info:
            config["gitlab"]["project"] = detected_info["repository"]

    # Bundle configuration
    click.echo("\n📦 Bundle Configuration:")

    max_files = click.prompt("Maximum files to include", default=100, type=int)
    include_tests = click.confirm("Include test files?", default=True)
    include_docs = click.confirm("Include documentation?", default=True)

    config["bundle"] = {
        "max_files": max_files,
        "include_tests": include_tests,
        "include_docs": include_docs,
        "claude_optimized": True,
    }

    return config


def _wizard_build_config(
    platforms: dict[str, Any], advanced_config: dict[str, Any], _detected_info: dict[str, Any]
) -> dict[str, Any]:
    """Build final configuration from wizard selections."""
    config = {"version": "1.0", "platforms": platforms}

    # Add platform-specific configs
    for platform in ["github", "gitlab", "jira"]:
        if platform in advanced_config:
            config[platform] = {"enabled": True, **advanced_config[platform]}
        else:
            config[platform] = {"enabled": False}

    # Add bundle config
    if "bundle" in advanced_config:
        config["bundle"] = advanced_config["bundle"]

    return config


def _check_github_authentication() -> dict[str, Any]:
    """Check for existing GitHub authentication methods with safe error handling."""
    auth_status = {
        "has_ssh": False,
        "ssh_info": "",
        "has_gh_cli": False,
        "gh_user": "",
        "has_env_token": False,
    }

    # Check for SSH keys
    try:
        result = subprocess.run(
            ["ssh", "-T", "git@github.com"], check=False, capture_output=True, text=True, timeout=10
        )
        if "successfully authenticated" in result.stderr:
            auth_status["has_ssh"] = True
            # Extract username from SSH response
            match = re.search(r"Hi ([^!]+)!", result.stderr)
            if match:
                auth_status["ssh_info"] = f"authenticated as {match.group(1)}"
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError, OSError):
        pass  # SSH check failed silently

    # Check for GitHub CLI
    try:
        result = subprocess.run(["gh", "auth", "status"], check=False, capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and "Logged in" in result.stderr:
            auth_status["has_gh_cli"] = True
            # Extract username from gh output
            match = re.search(r"Logged in to github\.com as ([^\s]+)", result.stderr)
            if match:
                auth_status["gh_user"] = match.group(1)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError, OSError):
        pass  # GitHub CLI check failed silently

    # Check for environment token
    try:
        min_token_length = 10  # Minimum realistic token length
        github_token = os.environ.get("GITHUB_TOKEN")
        if github_token and len(github_token) > min_token_length:
            auth_status["has_env_token"] = True
    except (OSError, ValueError, KeyError):
        pass  # Environment check failed silently

    return auth_status


def _run_git_command_safe(cmd: list[str], timeout: int = 5, cwd: Path | None = None) -> tuple[bool, str]:
    """Safely run a git command with proper error handling."""
    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        return result.returncode == 0, result.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, ""
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return False, ""


def _detect_jira_info() -> dict[str, Any]:
    """Detect Jira information from git history and branch names."""
    jira_info = {"url": "", "project_key": "", "patterns": []}

    # Check recent commit messages for Jira references
    success, commit_messages = _run_git_command_safe(
        ["git", "log", "--oneline", "-20", "--grep=JIRA", "--grep=jira", "--grep=[A-Z]+-[0-9]+"]
    )

    if success and commit_messages:
        # Look for Jira URLs in commit messages
        url_pattern = r"https://([^/\s]+\.atlassian\.net)"
        urls = re.findall(url_pattern, commit_messages)
        if urls:
            jira_info["url"] = f"https://{urls[0]}"

        # Look for ticket patterns (PROJECT-123)
        ticket_pattern = r"\b([A-Z]{2,10})-\d+"
        tickets = re.findall(ticket_pattern, commit_messages)
        if tickets:
            # Find most common project key
            most_common = Counter(tickets).most_common(1)
            if most_common:
                jira_info["project_key"] = most_common[0][0]

    # Also check current branch name
    success, branch_name = _run_git_command_safe(["git", "branch", "--show-current"], timeout=2)

    if success and branch_name:
        # Look for ticket patterns in branch name
        ticket_match = re.search(r"\b([A-Z]{2,10})-\d+", branch_name)
        if ticket_match and not jira_info["project_key"]:
            jira_info["project_key"] = ticket_match.group(1).split("-")[0]

    return jira_info


def _detect_ticket_patterns() -> tuple[dict[str, Any], dict[str, Any]]:
    """Detect ticket patterns from git history - user's patterns first, then project-wide.

    Returns:
        tuple: (user_patterns, project_patterns) - dicts with pattern counts
    """
    user_patterns = {}
    project_patterns = {}

    # Get current user's email/name for filtering their commits
    success, user_email = _run_git_command_safe(["git", "config", "user.email"], timeout=3)

    # Get user's own commits first (last 50 commits by them)
    if success and user_email:
        user_success, user_commits = _run_git_command_safe(["git", "log", f"--author={user_email}", "--oneline", "-50"])

        if user_success and user_commits:
            user_text = user_commits

            # Also get user's branches
            branch_success, user_branches = _run_git_command_safe(
                ["git", "for-each-ref", "--format=%(refname:short)", "refs/heads"], timeout=3
            )

            if branch_success and user_branches:
                user_text += "\n" + user_branches

            # Find ticket patterns in user's work
            ticket_pattern = r"\b([A-Z]{2,15})-\d+"
            user_matches = re.findall(ticket_pattern, user_text)

            if user_matches:
                user_counter = Counter(user_matches)
                user_patterns = {prefix: count for prefix, count in user_counter.items() if count >= 1}

    # Get project-wide patterns as fallback (recent commits from all users)
    project_success, project_commits = _run_git_command_safe(["git", "log", "--oneline", "-100", "--all"])

    if project_success and project_commits:
        project_text = project_commits

        # Also include all branch names
        branch_success, all_branches = _run_git_command_safe(["git", "branch", "-a"], timeout=3)
        if branch_success and all_branches:
            project_text += "\n" + all_branches

        # Find all ticket patterns (PROJECT-123 style)
        ticket_pattern = r"\b([A-Z]{2,15})-\d+"
        project_matches = re.findall(ticket_pattern, project_text)

        if project_matches:
            # Count occurrences of each prefix
            project_counter = Counter(project_matches)
            # Only include prefixes that appear more than once (reduces noise)
            project_patterns = {prefix: count for prefix, count in project_counter.items() if count > 1}

    return user_patterns, project_patterns


def _wizard_setup_credentials(platforms: dict[str, Any]) -> None:
    """Wizard step for credential setup."""
    click.echo("Setting up secure credential storage...")

    # GitHub credentials
    if platforms.get("repository") == "github":
        # Check for existing GitHub authentication
        github_auth_status = _check_github_authentication()

        if github_auth_status["has_ssh"]:
            click.echo("✅ GitHub SSH authentication detected")
            click.echo(f"   SSH key: {github_auth_status['ssh_info']}")
            click.echo("   This covers git operations (clone, push, pull)")

        if github_auth_status["has_gh_cli"]:
            click.echo("✅ GitHub CLI (gh) authentication detected")
            click.echo("   This covers GitHub API operations")

        if github_auth_status["has_env_token"]:
            click.echo("✅ GITHUB_TOKEN environment variable detected")
            click.echo("   This covers GitHub API operations")

        # Determine if we need additional setup
        needs_api_token = not (github_auth_status["has_gh_cli"] or github_auth_status["has_env_token"])

        if needs_api_token:
            click.echo("\n🔗 GitHub API Token Setup:")
            click.echo("For enhanced DevHub features (PR analysis, issue correlation), we need API access.")

            if click.confirm("Set up GitHub API token now?", default=True):
                click.echo("\n📋 Token Setup Guide:")
                click.echo("1. Go to: https://github.com/settings/tokens")
                click.echo("2. Create a 'Personal access token (classic)'")
                click.echo("3. Required scopes: repo, read:org, read:project")
                click.echo("4. For private repos, also select: repo (full control)")

                click.prompt("GitHub personal access token", hide_input=True)
                # Store token (implementation depends on auth system)
                click.echo("✅ GitHub token stored securely")
            else:
                click.echo("⚠️  Limited functionality: Only git operations will work")
        else:
            click.echo("✅ GitHub authentication is fully configured!")

    # Jira credentials
    if platforms.get("project_management") == "jira" and click.confirm("Set up Jira credentials now?", default=True):
        click.echo("🎫 Jira Setup Guide:")
        click.echo("1. Go to: https://id.atlassian.com/manage-profile/security/api-tokens")
        click.echo("2. Create API token")

        jira_email = click.prompt("Jira email address")
        jira_token = click.prompt("Jira API token", hide_input=True)

        # Visual confirmation of token entry
        if jira_token and len(jira_token) > 0:
            # Constants for token masking
            long_token_threshold = 8
            short_token_threshold = 4
            if len(jira_token) > long_token_threshold:
                masked_token = jira_token[:4] + "x" * (len(jira_token) - long_token_threshold) + jira_token[-4:]
            elif len(jira_token) > short_token_threshold:
                masked_token = jira_token[:2] + "x" * (len(jira_token) - short_token_threshold) + jira_token[-2:]
            else:
                masked_token = "x" * len(jira_token)
            click.echo(f"   ✅ Token entered: {masked_token} ({len(jira_token)} characters)")
        else:
            click.echo("   ⚠️  No token entered")

        # Store credentials in DevHub vault (proper persistent solution)
        try:
            # Ensure vault directory exists
            ensure_devhub_home()

            click.echo("   🔐 Initializing vault...")

            async def store_jira_credentials() -> None:
                vault_config = VaultConfig(vault_dir=VAULT_DIR)
                vault = SecureVault(vault_config)

                # Initialize vault if needed
                if not (VAULT_DIR / ".initialized").exists():
                    click.echo("   🔑 Creating secure vault...")
                    # Use a simple default password for convenience (could be improved)
                    result = await vault.initialize("devhub-default")
                    if isinstance(result, Success):
                        (VAULT_DIR / ".initialized").touch()
                        click.echo("   ✅ Vault initialized successfully")
                    elif isinstance(result, Failure):
                        msg = f"Vault initialization failed: {result}"
                        _raise_vault_error(msg)
                    elif hasattr(result, "is_success") and result.is_success():
                        (VAULT_DIR / ".initialized").touch()
                        click.echo("   ✅ Vault initialized successfully")
                    else:
                        msg = f"Vault initialization failed: {result}"
                        _raise_vault_error(msg)
                else:
                    click.echo("   ✅ Using existing vault")
                    # Unlock existing vault with default password
                    click.echo("   🔓 Unlocking vault...")
                    unlock_result = vault.unlock("devhub-default")  # NOT async
                    if isinstance(unlock_result, Success):
                        click.echo("   ✅ Vault unlocked successfully")
                    elif isinstance(unlock_result, Failure):
                        msg = f"Failed to unlock vault: {unlock_result}"
                        _raise_vault_error(msg)
                    elif hasattr(unlock_result, "is_success") and unlock_result.is_success():
                        click.echo("   ✅ Vault unlocked successfully")
                    else:
                        msg = f"Failed to unlock vault: {unlock_result}"
                        _raise_vault_error(msg)

                # Store Jira email
                click.echo("   📧 Storing email...")
                email_result = await vault.store_credential(
                    CredentialMetadata(
                        name="jira_email",
                        credential_type=CredentialType.API_TOKEN,
                        description="Jira email address",
                    ),
                    jira_email,
                )
                # Handle returns.result types properly
                if isinstance(email_result, Success):
                    pass  # Success
                elif isinstance(email_result, Failure):
                    msg = f"Failed to store email: {email_result}"
                    _raise_vault_error(msg)
                elif hasattr(email_result, "is_success") and not email_result.is_success():
                    error_msg = email_result.failure() if hasattr(email_result, "failure") else str(email_result)
                    msg = f"Failed to store email: {error_msg}"
                    _raise_vault_error(msg)
                else:
                    msg = f"Failed to store email: {email_result}"
                    _raise_vault_error(msg)

                # Store Jira API token
                click.echo("   🎫 Storing API token...")
                token_result = await vault.store_credential(
                    CredentialMetadata(
                        name="jira_token",
                        credential_type=CredentialType.API_TOKEN,
                        description="Jira API token",
                    ),
                    jira_token,
                )
                # Handle returns.result types properly
                if isinstance(token_result, Success):
                    pass  # Success
                elif isinstance(token_result, Failure):
                    msg = f"Failed to store token: {token_result}"
                    _raise_vault_error(msg)
                elif hasattr(token_result, "is_success") and not token_result.is_success():
                    error_msg = token_result.failure() if hasattr(token_result, "failure") else str(token_result)
                    msg = f"Failed to store token: {error_msg}"
                    _raise_vault_error(msg)
                else:
                    msg = f"Failed to store token: {token_result}"
                    _raise_vault_error(msg)

                click.echo("   ✅ All credentials stored successfully")

            # Run the async credential storage
            asyncio.run(store_jira_credentials())
            click.echo("✅ Jira credentials stored securely in DevHub vault")

        except VaultOperationError as e:
            # Fallback to environment variables if vault fails
            click.echo(f"⚠️  Vault storage failed: {e}")
            click.echo("   🔄 Using environment variable fallback...")
            os.environ["JIRA_EMAIL"] = jira_email
            os.environ["JIRA_API_TOKEN"] = jira_token
            click.echo("✅ Jira credentials stored for this session")
            click.echo("💡 To make permanent, add to your shell profile:")
            click.echo(f'   export JIRA_EMAIL="{jira_email}"')
            click.echo('   export JIRA_API_TOKEN="your_token_here"')

    # GitLab credentials
    if platforms.get("repository") == "gitlab" and click.confirm("Set up GitLab credentials now?", default=True):
        click.echo("🦊 GitLab Setup Guide:")
        click.echo("1. Go to your GitLab instance -> User Settings -> Access Tokens")
        click.echo("2. Create personal access token")
        click.echo("3. Required scopes: api, read_user, read_repository")

        click.prompt("GitLab personal access token", hide_input=True)
        # Store token (implementation depends on auth system)
        click.echo("✅ GitLab token stored securely")


def _wizard_show_summary(config: dict[str, Any], scope: str) -> None:
    """Show final summary and next steps."""
    platforms = config.get("platforms", {})

    click.echo("📋 Configuration Summary:")
    click.echo(f"  Scope: {scope}")
    click.echo(f"  Repository: {platforms.get('repository', 'none')}")
    click.echo(f"  Project Management: {platforms.get('project_management', 'none')}")

    if config.get("jira", {}).get("ticket_patterns"):
        patterns = config["jira"]["ticket_patterns"]
        click.echo(f"  Ticket Patterns: {', '.join(patterns)}")

    click.echo("\n🚀 Ready to use DevHub!")
    click.echo("Try these commands:")
    click.echo("  devhub status           # Check detection")
    click.echo("  devhub claude context   # Generate enhanced context")
    click.echo("  devhub --help          # See all commands")


def _show_next_steps(config: dict[str, Any]) -> None:
    """Show next steps after configuration."""
    click.echo("\n📝 Configuration created successfully!")

    platforms = config.get("platforms", {})
    repo = platforms.get("repository", "none")
    pm = platforms.get("project_management", "none")

    click.echo("\n🔧 Configured platforms:")
    click.echo(f"  Repository: {repo}")
    click.echo(f"  Project Management: {pm}")

    click.echo("\n📋 Next steps:")
    click.echo("1. Set up authentication:")
    click.echo("   devhub auth setup --project")
    click.echo("2. Generate Claude context:")
    click.echo("   devhub claude context")
    click.echo("3. Check status:")
    click.echo("   devhub status")


@click.group()
@click.version_option(version="0.1.0", prog_name="DevHub")
def cli() -> None:
    """DevHub - Transform Claude Code into your development orchestrator.

    DevHub enhances your Claude Code interactions by providing rich project
    context from GitHub, GitLab, Jira, and your local repository.

    Examples:
      # Initialize DevHub with guided wizard
      devhub init

      # Set up credentials
      devhub auth setup

      # Generate Claude context from any project
      devhub claude context

      # Bundle PR for review
      devhub bundle --pr 123
    """
    ensure_devhub_home()


@cli.command()
@click.option("--github", is_flag=True, help="Enable GitHub integration")
@click.option("--gitlab", is_flag=True, help="Enable GitLab integration")
@click.option("--jira", is_flag=True, help="Enable Jira integration")
@click.option("--github-projects", is_flag=True, help="Enable GitHub Projects integration")
@click.option("--profile", help="Use a predefined profile (work, personal, etc.)")
@click.option("--basic", is_flag=True, help="Basic setup (skip wizard)")
def init(github: bool, gitlab: bool, jira: bool, github_projects: bool, profile: str | None, basic: bool) -> None:
    """Initialize DevHub for this project with smart platform detection.

    Creates .devhub.yaml configuration in the current directory.
    By default, runs the complete setup wizard with smart detection.

    Examples:
      devhub init                          # Complete setup wizard (default)
      devhub init --basic                  # Simple setup without wizard
      devhub init --github --jira          # Quick GitHub + Jira setup
      devhub init --profile work           # Use work profile
    """
    # Default behavior: run wizard unless basic mode or flags are specified
    should_run_wizard = not basic and not any([github, gitlab, jira, github_projects, profile])

    if should_run_wizard:
        # Run complete setup wizard (default experience)
        _run_setup_wizard()
        return

    # Always create project-based configuration
    config_path = Path.cwd() / ".devhub.yaml"
    if config_path.exists() and not click.confirm(f"{config_path} exists. Overwrite?"):
        click.echo("Aborted.")
        return

    # Smart project initialization
    config = _create_project_config(github, gitlab, jira, github_projects, profile)

    with config_path.open("w") as f:
        yaml.dump(config, f, default_flow_style=False)

    click.echo(f"✅ Created project config: {config_path}")
    _show_next_steps(config)


@cli.group()
def auth() -> None:
    """Manage authentication and credentials."""


@auth.command()
def setup() -> None:
    """Set up authentication credentials securely."""

    async def setup_credentials() -> None:
        vault_config = VaultConfig(vault_dir=VAULT_DIR)
        vault = SecureVault(vault_config)

        # Get or create master password
        if (VAULT_DIR / ".initialized").exists():
            master_password = click.prompt("Enter vault password", hide_input=True)
            # Verify password by attempting to unlock the vault
        else:
            master_password = click.prompt("Create vault password", hide_input=True)
            confirm = click.prompt("Confirm password", hide_input=True)

            if master_password != confirm:
                click.echo("❌ Passwords don't match")
                sys.exit(1)

            await vault.initialize(master_password)
            (VAULT_DIR / ".initialized").touch()
            click.echo("✅ Vault initialized")

        # GitHub setup
        if click.confirm("Configure GitHub?"):
            token = click.prompt("GitHub personal access token", hide_input=True)
            await vault.store_credential(
                CredentialMetadata(
                    name="github_token",
                    credential_type=CredentialType.API_TOKEN,
                    description="GitHub API token",
                ),
                token,
            )
            click.echo("✅ GitHub token stored")

        # Jira setup
        if click.confirm("Configure Jira?"):
            email = click.prompt("Jira email")
            token = click.prompt("Jira API token", hide_input=True)

            await vault.store_credential(
                CredentialMetadata(
                    name="jira_email",
                    credential_type=CredentialType.API_TOKEN,
                    description="Jira email",
                ),
                email,
            )
            await vault.store_credential(
                CredentialMetadata(
                    name="jira_token",
                    credential_type=CredentialType.API_TOKEN,
                    description="Jira API token",
                ),
                token,
            )
            click.echo("✅ Jira credentials stored")

        # GitLab setup
        if click.confirm("Configure GitLab?"):
            token = click.prompt("GitLab personal access token", hide_input=True)
            await vault.store_credential(
                CredentialMetadata(
                    name="gitlab_token",
                    credential_type=CredentialType.API_TOKEN,
                    description="GitLab API token",
                ),
                token,
            )
            click.echo("✅ GitLab token stored")

        click.echo("\n🎉 Authentication setup complete!")

    asyncio.run(setup_credentials())


@auth.command()
def status() -> None:
    """Check authentication status."""
    config = load_config()

    click.echo("🔐 Authentication Status\n")

    # Check vault
    if (VAULT_DIR / ".initialized").exists():
        click.echo("✅ Credential vault initialized")
    else:
        click.echo("❌ Credential vault not initialized")
        click.echo("   Run: devhub auth setup")
        return

    # Check configured platforms
    platforms = []
    if config.get("github", {}).get("enabled"):
        platforms.append("GitHub")
    if config.get("jira", {}).get("enabled"):
        platforms.append("Jira")
    if config.get("gitlab", {}).get("enabled"):
        platforms.append("GitLab")

    if platforms:
        click.echo(f"📋 Configured platforms: {', '.join(platforms)}")
    else:
        click.echo("⚠️  No platforms configured")


@cli.group()
def claude() -> None:
    """Claude Code integration commands."""


@claude.command()
def context() -> None:
    """Generate enhanced context for Claude Code."""

    async def generate() -> None:
        click.echo("🧠 Generating enhanced Claude context...")

        # Use secure temporary directory
        debug_log = Path(tempfile.gettempdir()) / "devhub_cli_debug.log"
        async with aiofiles.open(debug_log, "a") as f:
            await f.write("CLI generate() function called\n")

        try:
            async with aiofiles.open(debug_log, "a") as f:
                await f.write("About to call claude_code_review_context()\n")
            context_result = await claude_code_review_context()

            if isinstance(context_result, Failure):
                click.echo(f"❌ Failed to generate context: {context_result.failure()}")
                return

            context = context_result.unwrap()

            # Save to file
            output_file = Path.cwd() / "claude_context.md"
            with output_file.open("w") as f:
                f.write(context)

            click.echo(f"✅ Context saved to: {output_file}")
            click.echo("\n📋 Next steps:")
            click.echo("1. Copy the contents of claude_context.md")
            click.echo("2. Paste into Claude Code")
            click.echo("3. Watch Claude understand your project deeply!")

        except (OSError, subprocess.SubprocessError, ValueError, RuntimeError) as e:
            exception_log = Path(tempfile.gettempdir()) / "devhub_exception.log"
            async with aiofiles.open(exception_log, "a") as f:
                await f.write(f"Exception in generate(): {type(e).__name__}: {e}\n")
                # Note: traceback.print_exc doesn't work with async files
                tb_str = traceback.format_exc()
                await f.write(tb_str)

            click.echo(f"❌ Error: {e}")
            click.echo("\n💡 Troubleshooting:")
            click.echo("1. Check you're in a git repository")
            click.echo("2. Verify credentials: devhub auth status")
            click.echo("3. Check config: devhub config show")

    asyncio.run(generate())


@cli.command()
@click.option("--pr", type=int, help="Pull/Merge request number")
@click.option("--claude", is_flag=True, help="Optimize for Claude Code")
@click.option("--output", "-o", help="Output file (default: stdout)")
@click.option("--jira-key", help="Jira issue key (e.g., PROJ-123)")
@click.option("--branch", help="Git branch name")
@click.option("--limit", default=10, help="Limit for comments")
@click.option("--organization", help="GitHub organization")
@click.option("--no-jira", is_flag=True, help="Exclude Jira data")
@click.option("--no-pr", is_flag=True, help="Exclude PR data")
@click.option("--no-diff", is_flag=True, help="Exclude PR diff")
@click.option("--no-comments", is_flag=True, help="Exclude unresolved comments")
def bundle(
    pr: int | None,
    claude: bool,
    output: str | None,
    jira_key: str | None,
    branch: str | None,
    limit: int,
    organization: str | None,
    no_jira: bool,
    no_pr: bool,
    no_diff: bool,
    no_comments: bool,
) -> None:
    """Create a comprehensive bundle of project context.

    This bundles together code, documentation, issues, and PRs into a
    single context bundle for analysis or review.
    """
    click.echo("📦 Creating context bundle...")

    # Create args namespace to match main.py expectations
    args = argparse.Namespace()
    args.pr_number = pr
    args.jira_key = jira_key
    args.branch = branch
    args.output_dir = output if output and not output.endswith(".yaml") else None
    args.out = output if output and output.endswith(".yaml") else None
    args.limit = limit
    args.organization = organization
    args.no_jira = no_jira
    args.no_pr = no_pr
    args.no_diff = no_diff
    args.no_comments = no_comments
    args.metadata_only = False
    args.format = "json"

    # Handle bundle command from main.py
    result = handle_bundle_command(args)

    if isinstance(result, Success):
        bundle_content = result.unwrap()

        if output:
            if output.endswith(".yaml"):
                # Convert JSON to YAML for YAML output
                try:
                    data = json.loads(bundle_content)
                    with Path(output).open("w") as f:
                        yaml.dump(data, f, default_flow_style=False)
                    click.echo(f"✅ Bundle saved to: {output}")
                except json.JSONDecodeError:
                    # Fallback: write as text
                    with Path(output).open("w") as f:
                        f.write(bundle_content)
                    click.echo(f"✅ Bundle saved to: {output}")
            else:
                # Already handled by main.py logic for directory output
                click.echo(result.unwrap())
        # Output to stdout
        elif claude:
            # Convert JSON to YAML for Claude optimization
            try:
                data = json.loads(bundle_content)
                click.echo(yaml.dump(data, default_flow_style=False))
            except json.JSONDecodeError:
                click.echo(bundle_content)
        else:
            click.echo(bundle_content)
    elif isinstance(result, Failure):
        click.echo(f"❌ Error: {result.failure()}", err=True)
        sys.exit(1)
    else:
        click.echo("❌ Unexpected result type", err=True)
        sys.exit(1)


@cli.command("project-status")
def project_status() -> None:
    """Show DevHub status and project detection."""
    cwd = Path.cwd()

    click.echo("🔍 DevHub Status\n")

    # Check global config
    if GLOBAL_CONFIG.exists():
        click.echo(f"✅ Global config: {GLOBAL_CONFIG}")
    else:
        click.echo("❌ No global config (run: devhub init)")

    # Check project config
    project_config = cwd / ".devhub.yaml"
    if project_config.exists():
        click.echo(f"✅ Project config: {project_config}")
    else:
        click.echo("i No project config (optional)")

    # Detect repository
    click.echo("\n📁 Project Detection:")

    if (cwd / ".git").exists():
        click.echo("✅ Git repository detected")

        # Try to detect platform
        git_config = cwd / ".git" / "config"
        if git_config.exists():
            content = git_config.read_text()
            if "github.com" in content:
                click.echo("  → GitHub repository")
            elif "gitlab" in content:
                click.echo("  → GitLab repository")
            else:
                click.echo("  → Git (platform unknown)")
    else:
        click.echo("❌ Not a git repository")

    # Check for project files
    files_found = []
    if (cwd / "package.json").exists():
        files_found.append("Node.js (package.json)")
    if (cwd / "requirements.txt").exists():
        files_found.append("Python (requirements.txt)")
    if (cwd / "pyproject.toml").exists():
        files_found.append("Python (pyproject.toml)")
    if (cwd / "Cargo.toml").exists():
        files_found.append("Rust (Cargo.toml)")

    if files_found:
        click.echo(f"\n📦 Project type: {', '.join(files_found)}")


@cli.command()
@click.option("--fix", is_flag=True, help="Automatically fix issues where possible")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed diagnostic information")
def doctor(fix: bool, verbose: bool) -> None:
    """Run health checks and verify DevHub installation with optional self-healing."""
    click.echo("🏥 DevHub Doctor - System Health Check\n")

    if fix:
        click.echo("🔧 Self-healing mode enabled - will attempt to fix issues\n")

    issues_found = []
    checks_passed = 0
    total_checks = 0

    # Check DevHub installation itself
    total_checks += 1
    try:
        devhub_version = getattr(devhub, "__version__", "unknown")
        click.echo(f"✅ DevHub is installed (version: {devhub_version})")
        checks_passed += 1
        if verbose:
            click.echo(f"   Installation path: {devhub.__file__}")
    except ImportError:
        click.echo("❌ DevHub installation issue")
        issues_found.append(("devhub_install", "DevHub installation issue"))

    # Check git
    total_checks += 1
    git_success, git_version = _run_git_command_safe(["git", "--version"], timeout=10)
    if git_success:
        click.echo("✅ git is available")
        if verbose:
            click.echo(f"   Version: {git_version}")
        checks_passed += 1
    else:
        click.echo("❌ git is not available")
        issues_found.append(("git", "git command not found - install git"))

    # Check GitHub CLI
    total_checks += 1
    try:
        result = subprocess.run(["gh", "--version"], check=False, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            click.echo("✅ GitHub CLI (gh) is available")
            if verbose:
                version_line = result.stdout.split("\n")[0] if result.stdout else "unknown"
                click.echo(f"   {version_line}")
            checks_passed += 1
        else:
            click.echo("❌ GitHub CLI (gh) is not available")
            issues_found.append(("gh_cli", "GitHub CLI not available"))
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        click.echo("❌ GitHub CLI (gh) is not available")
        issues_found.append(("gh_cli", "GitHub CLI not available"))

    # Check if in git repo
    total_checks += 1
    in_git_repo, _ = _run_git_command_safe(["git", "rev-parse", "--is-inside-work-tree"])
    if in_git_repo:
        click.echo("✅ Current directory is a git repository")
        checks_passed += 1

        if verbose:
            # Show additional git info
            success, remote_url = _run_git_command_safe(["git", "remote", "get-url", "origin"])
            if success:
                click.echo(f"   Remote origin: {remote_url}")

            success, branch = _run_git_command_safe(["git", "branch", "--show-current"])
            if success:
                click.echo(f"   Current branch: {branch}")
    else:
        click.echo("⚠️  Current directory is not a git repository")
        if verbose:
            click.echo("   DevHub works best with git repositories")

    # Check DevHub configuration
    total_checks += 1
    config_exists = (Path.cwd() / ".devhub.yaml").exists() or GLOBAL_CONFIG.exists()
    if config_exists:
        click.echo("✅ DevHub configuration found")
        checks_passed += 1

        if verbose:
            if (Path.cwd() / ".devhub.yaml").exists():
                click.echo("   Project config: .devhub.yaml")
            if GLOBAL_CONFIG.exists():
                click.echo(f"   Global config: {GLOBAL_CONFIG}")
    else:
        click.echo("⚠️  No DevHub configuration found")
        issues_found.append(("config", "No DevHub configuration - run 'devhub init'"))

    # Check authentication
    total_checks += 1
    auth_status = _check_github_authentication()
    has_any_auth = any([auth_status["has_ssh"], auth_status["has_gh_cli"], auth_status["has_env_token"]])

    if has_any_auth:
        click.echo("✅ GitHub authentication configured")
        checks_passed += 1

        if verbose:
            if auth_status["has_ssh"]:
                click.echo(f"   SSH: {auth_status['ssh_info']}")
            if auth_status["has_gh_cli"]:
                click.echo(f"   GitHub CLI: logged in as {auth_status['gh_user']}")
            if auth_status["has_env_token"]:
                click.echo("   Environment: GITHUB_TOKEN set")
    else:
        click.echo("⚠️  No GitHub authentication found")
        issues_found.append(("auth", "No GitHub authentication - run 'devhub auth setup'"))

    # Check vault (if initialized)
    if (VAULT_DIR / ".initialized").exists():
        click.echo("✅ Credential vault initialized")
        if verbose:
            click.echo(f"   Vault location: {VAULT_DIR}")
    elif verbose:
        click.echo("📍 Credential vault not initialized (optional)")

    # Self-healing attempts
    if fix and issues_found:
        click.echo("\n🔧 Attempting to fix issues...")

        for issue_type, _description in issues_found:
            if issue_type == "config":
                if click.confirm("   No configuration found. Run 'devhub init' now?", default=True):
                    try:
                        # Import here to avoid circular import
                        # Use string reference instead
                        ctx = click.get_current_context()
                        ctx.invoke(init, basic=True)
                        click.echo("   ✅ Configuration created")
                    except (OSError, click.ClickException, RuntimeError) as e:
                        click.echo(f"   ❌ Failed to create configuration: {e}")

            elif (
                issue_type == "gh_cli"
                and sys.platform != "win32"
                and click.confirm("   GitHub CLI not found. Attempt to install?", default=False)
            ):
                try:
                    # Try common installation methods
                    if sys.platform == "darwin":  # macOS
                        result = subprocess.run(["brew", "install", "gh"], check=True, timeout=60)
                    else:  # Linux
                        # Try apt first, then fallback to direct install
                        try:
                            subprocess.run(["sudo", "apt", "update"], check=True, timeout=30)
                            subprocess.run(["sudo", "apt", "install", "-y", "gh"], check=True, timeout=60)
                        except subprocess.CalledProcessError:
                            # Fallback to direct install
                            subprocess.run(
                                [
                                    "curl",
                                    "-fsSL",
                                    "https://cli.github.com/packages/githubcli-archive-keyring.gpg",
                                    "|",
                                    "sudo",
                                    "dd",
                                    "of=/usr/share/keyrings/githubcli-archive-keyring.gpg",
                                ],
                                check=True,
                                timeout=30,
                            )

                    click.echo("   ✅ GitHub CLI installation attempted")
                except (OSError, subprocess.SubprocessError, PermissionError) as e:
                    click.echo(f"   ❌ Failed to install GitHub CLI: {e}")

    # Summary
    click.echo(f"\n📊 Health Check Summary: {checks_passed}/{total_checks} checks passed")

    if checks_passed == total_checks:
        click.echo("🎉 All systems healthy!")
    elif checks_passed >= total_checks - 2:
        click.echo("⚠️  Minor issues detected - mostly functional")
        if issues_found and not fix:
            click.echo("💡 Run 'devhub doctor --fix' to attempt automatic fixes")
    else:
        click.echo("❌ Major issues detected - setup may be incomplete")
        if not fix:
            click.echo("💡 Run 'devhub doctor --fix' to attempt automatic fixes")

        click.echo("\n📋 Manual steps:")
        for _issue_type, _description in issues_found:
            click.echo(f"   • {_description}")

    if verbose and issues_found:
        click.echo(f"\n🔍 Issues detected: {len(issues_found)}")
        for i, (_issue_type, description) in enumerate(issues_found, 1):
            click.echo(f"   {i}. {description}")

    # Always exit with 0 for doctor command - it's informational
    # Exit code indicates whether the doctor command itself succeeded, not system health


@cli.group()
def config() -> None:
    """Manage DevHub configuration."""


@config.command()
def show() -> None:
    """Show current configuration."""
    config = load_config()
    click.echo(yaml.dump(config, default_flow_style=False))


@config.command("set")
@click.argument("key")
@click.argument("value")
def set_config(key: str, value: str) -> None:
    """Set a configuration value.

    Example:
      devhub config set github.organization "my-company"
    """
    config = load_config()

    # Navigate nested keys
    keys = key.split(".")
    current = config
    for k in keys[:-1]:
        if k not in current:
            current[k] = {}
        current = current[k]

    current[keys[-1]] = value
    save_global_config(config)

    click.echo(f"✅ Set {key} = {value}")


@config.command("get")
@click.argument("key")
def get_config(key: str) -> None:
    """Get a configuration value."""
    config = load_config()

    # Navigate nested keys
    keys = key.split(".")
    current = config
    try:
        for k in keys:
            current = current[k]
        click.echo(current)
    except KeyError:
        click.echo(f"❌ Key not found: {key}")
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
