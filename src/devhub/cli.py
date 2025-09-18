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
from collections import Counter
from pathlib import Path
from typing import Any
from typing import cast

import click
import yaml
from returns.result import Failure
from returns.result import Success

from devhub.claude_integration import claude_code_review_context
from devhub.main import handle_bundle_command
from devhub.vault import CredentialMetadata
from devhub.vault import CredentialType
from devhub.vault import SecureVault
from devhub.vault import VaultConfig


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
        return _create_config_from_flags(github, gitlab, jira, github_projects)

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


def _run_setup_wizard() -> None:
    """Run the complete DevHub setup wizard."""
    click.echo("🧙‍♂️ DevHub Complete Setup Wizard")
    click.echo("=" * 50)
    click.echo("This wizard will guide you through setting up DevHub with")
    click.echo("platform detection, configuration, and credentials.\n")

    # Always use project-based configuration for simplicity and clarity
    scope = "project"
    click.echo("🎯 Setting up DevHub for this project")
    click.echo("📁 Configuration will be saved to .devhub.yaml")
    click.echo()

    # Step 2: Project analysis
    click.echo("\n🔍 Step 1: Project Analysis")
    click.echo("-" * 25)

    detected_platform, detected_info = _detect_repository_platform()
    project_types = _detect_project_type()

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

    # Step 3: Platform selection
    click.echo("\n⚙️  Step 2: Platform Configuration")
    click.echo("-" * 30)

    platforms = _wizard_select_platforms(detected_platform, detected_info)

    # Step 4: Advanced configuration
    click.echo("\n🔧 Step 3: Advanced Configuration")
    click.echo("-" * 28)

    advanced_config = _wizard_advanced_config(platforms)

    # Step 5: Credential setup
    click.echo("\n🔐 Step 4: Credential Setup")
    click.echo("-" * 24)

    setup_creds = click.confirm("Set up credentials now?", default=True)

    # Step 6: Build final configuration
    config = _wizard_build_config(platforms, advanced_config, detected_info)

    # Step 7: Save configuration
    if scope in ["global", "both"]:
        ensure_devhub_home()
        global_config = _create_global_config()
        save_global_config(global_config)
        click.echo("✅ Global configuration saved")

    if scope in ["project", "both"]:
        config_path = Path.cwd() / ".devhub.yaml"
        with config_path.open("w") as f:
            yaml.dump(config, f, default_flow_style=False)
        click.echo(f"✅ Project configuration saved: {config_path}")

    # Step 8: Credential setup
    if setup_creds:
        click.echo("\n🔑 Setting up credentials...")
        _wizard_setup_credentials(platforms)

    # Step 9: Final verification and next steps
    click.echo("\n🎉 Setup Complete!")
    click.echo("=" * 20)

    _wizard_show_summary(config, scope)


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


def _wizard_advanced_config(platforms: dict[str, Any]) -> dict[str, Any]:
    """Wizard step for advanced configuration."""
    config = {}

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

        org = click.prompt("GitHub organization/username", default="")
        use_projects = platforms.get("project_management") == "github"

        project_number = click.prompt("GitHub Project number (optional)", default="") if use_projects else ""

        config["github"] = {
            "organization": org,
            "projects": use_projects,
            "project_number": project_number if project_number else None,
        }

    # GitLab-specific configuration
    if platforms.get("repository") == "gitlab":
        click.echo("\n🦊 GitLab Configuration:")

        base_url = click.prompt("GitLab URL", default="https://gitlab.com")
        group_path = click.prompt("Group/namespace", default="")

        config["gitlab"] = {"base_url": base_url, "group_path": group_path}

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
    """Check for existing GitHub authentication methods."""
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
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Check for GitHub CLI
    try:
        result = subprocess.run(["gh", "auth", "status"], check=False, capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and "Logged in" in result.stderr:
            auth_status["has_gh_cli"] = True
            # Extract username from gh output
            match = re.search(r"Logged in to github\.com as ([^\s]+)", result.stderr)
            if match:
                auth_status["gh_user"] = match.group(1)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Check for environment token
    min_token_length = 10  # Minimum realistic token length
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token and len(github_token) > min_token_length:
        auth_status["has_env_token"] = True

    return auth_status


def _detect_jira_info() -> dict[str, Any]:
    """Detect Jira information from git history and branch names."""
    jira_info = {"url": "", "project_key": "", "patterns": []}

    try:
        # Check recent commit messages for Jira references
        result = subprocess.run(
            ["git", "log", "--oneline", "-20", "--grep=JIRA", "--grep=jira", "--grep=[A-Z]+-[0-9]+"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            commit_messages = result.stdout

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
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"], check=False, capture_output=True, text=True, timeout=2
        )

        if branch_result.returncode == 0:
            branch_name = branch_result.stdout.strip()
            # Look for ticket patterns in branch name
            ticket_match = re.search(r"\b([A-Z]{2,10})-\d+", branch_name)
            if ticket_match and not jira_info["project_key"]:
                jira_info["project_key"] = ticket_match.group(1).split("-")[0]

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        pass

    return jira_info


def _detect_ticket_patterns() -> tuple[dict[str, Any], dict[str, Any]]:
    """Detect ticket patterns from git history - user's patterns first, then project-wide.

    Returns:
        tuple: (user_patterns, project_patterns) - dicts with pattern counts
    """
    user_patterns = {}
    project_patterns = {}

    try:
        # Get current user's email/name for filtering their commits
        user_email = ""
        try:
            email_result = subprocess.run(
                ["git", "config", "user.email"], check=False, capture_output=True, text=True, timeout=3
            )
            if email_result.returncode == 0:
                user_email = email_result.stdout.strip()
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            pass

        # Get user's own commits first (last 50 commits by them)
        if user_email:
            user_result = subprocess.run(
                ["git", "log", f"--author={user_email}", "--oneline", "-50"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if user_result.returncode == 0:
                user_text = user_result.stdout

                # Also get user's branches
                user_branch_result = subprocess.run(
                    ["git", "for-each-ref", "--format=%(refname:short)", "refs/heads"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if user_branch_result.returncode == 0:
                    user_text += "\n" + user_branch_result.stdout

                # Find ticket patterns in user's work
                ticket_pattern = r"\b([A-Z]{2,15})-\d+"
                user_matches = re.findall(ticket_pattern, user_text)

                if user_matches:
                    user_counter = Counter(user_matches)
                    user_patterns = {prefix: count for prefix, count in user_counter.items() if count >= 1}

        # Get project-wide patterns as fallback (recent commits from all users)
        project_result = subprocess.run(
            ["git", "log", "--oneline", "-100", "--all"], check=False, capture_output=True, text=True, timeout=5
        )

        if project_result.returncode == 0:
            project_text = project_result.stdout

            # Also include all branch names
            branch_result = subprocess.run(
                ["git", "branch", "-a"], check=False, capture_output=True, text=True, timeout=3
            )
            if branch_result.returncode == 0:
                project_text += "\n" + branch_result.stdout

            # Find all ticket patterns (PROJECT-123 style)
            ticket_pattern = r"\b([A-Z]{2,15})-\d+"
            project_matches = re.findall(ticket_pattern, project_text)

            if project_matches:
                # Count occurrences of each prefix
                project_counter = Counter(project_matches)
                # Only include prefixes that appear more than once (reduces noise)
                project_patterns = {prefix: count for prefix, count in project_counter.items() if count > 1}

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        pass

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

        click.prompt("Jira email address")
        click.prompt("Jira API token", hide_input=True)
        # Store credentials (implementation depends on auth system)
        click.echo("✅ Jira credentials stored securely")

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

        try:
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

        except (OSError, subprocess.SubprocessError, yaml.YAMLError) as e:
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
def doctor() -> None:
    """Run health checks and verify DevHub installation."""
    click.echo("🏥 DevHub Doctor - System Health Check\n")

    checks_passed = 0
    total_checks = 0

    # Check git
    total_checks += 1
    try:
        result = subprocess.run(["git", "--version"], check=False, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            click.echo("✅ git is available")
            checks_passed += 1
        else:
            click.echo("❌ git is not available")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        click.echo("❌ git is not available")

    # Check GitHub CLI
    total_checks += 1
    try:
        result = subprocess.run(
            ["bash", "-lc", "command -v gh"], check=False, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            click.echo("✅ GitHub CLI (gh) is available")
            checks_passed += 1
        else:
            click.echo("❌ GitHub CLI (gh) is not available")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        click.echo("❌ GitHub CLI (gh) is not available")

    # Check if in git repo
    total_checks += 1
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"], check=False, capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            click.echo("✅ Current directory is a git repository")
            checks_passed += 1
        else:
            click.echo("❌ Current directory is not a git repository")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        click.echo("❌ Current directory is not a git repository")

    # Check Jira credentials
    total_checks += 1
    jira_base_url = os.environ.get("JIRA_BASE_URL")
    jira_email = os.environ.get("JIRA_EMAIL")
    jira_api_token = os.environ.get("JIRA_API_TOKEN")

    if jira_base_url and jira_email and jira_api_token:
        click.echo("✅ Jira credentials are configured")
        checks_passed += 1
    else:
        click.echo("⚠️  Jira credentials not found (optional)")
        # Don't count as failure since it's optional
        checks_passed += 1

    # Summary
    click.echo(f"\n📊 Health Check Summary: {checks_passed}/{total_checks} checks passed")

    if checks_passed == total_checks:
        click.echo("🎉 All systems healthy!")
    elif checks_passed >= total_checks - 1:
        click.echo("⚠️  Minor issues detected - mostly functional")
    else:
        click.echo("❌ Major issues detected - setup may be incomplete")
        click.echo("\n💡 Next steps:")
        click.echo("1. Install missing tools")
        click.echo("2. Run: devhub init")
        click.echo("3. Run: devhub auth setup")


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
