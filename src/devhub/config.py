"""Configuration system for DevHub with organization-specific settings.

This module provides immutable configuration structures and loading functions
following functional programming principles. All configurations are frozen
dataclasses to ensure immutability and thread safety.
"""

import json
import os
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any
from typing import cast

from returns.result import Failure
from returns.result import Result
from returns.result import Success


@dataclass(frozen=True, slots=True)
class JiraConfig:
    """Immutable Jira-specific configuration."""

    default_project_prefix: str | None = None
    base_url: str | None = None
    email: str | None = None
    api_token: str | None = None
    timeout_seconds: int = 30
    max_retries: int = 3


@dataclass(frozen=True, slots=True)
class GitHubConfig:
    """Immutable GitHub-specific configuration."""

    default_org: str | None = None
    timeout_seconds: int = 30
    max_retries: int = 3
    use_ssh: bool = False


@dataclass(frozen=True, slots=True)
class OutputConfig:
    """Immutable output-specific configuration."""

    base_directory: str = "review-bundles"
    include_timestamps: bool = True
    file_permissions: int = 0o644
    directory_permissions: int = 0o755


@dataclass(frozen=True, slots=True)
class BundleDefaults:
    """Immutable default bundle configuration."""

    include_jira: bool = True
    include_pr: bool = True
    include_diff: bool = True
    include_comments: bool = True
    comment_limit: int = 10
    diff_context_lines: int = 3


@dataclass(frozen=True, slots=True)
class OrganizationConfig:
    """Immutable organization-specific configuration.

    This allows different organizations to have their own defaults
    for Jira project prefixes, GitHub settings, and bundle preferences.
    """

    name: str
    jira: JiraConfig = field(default_factory=JiraConfig)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    bundle_defaults: BundleDefaults = field(default_factory=BundleDefaults)
    description: str | None = None


@dataclass(frozen=True, slots=True)
class DevHubConfig:
    """Immutable main configuration for DevHub.

    Contains global settings and organization-specific configurations.
    Multiple organizations can be configured, with one set as default.
    """

    default_organization: str | None = None
    organizations: tuple[OrganizationConfig, ...] = field(default_factory=tuple)
    global_jira: JiraConfig = field(default_factory=JiraConfig)
    global_github: GitHubConfig = field(default_factory=GitHubConfig)
    global_output: OutputConfig = field(default_factory=OutputConfig)
    config_version: str = "1.0"

    def get_organization(self, name: str) -> OrganizationConfig | None:
        """Get organization configuration by name."""
        for org in self.organizations:
            if org.name == name:
                return org
        return None

    def get_default_organization(self) -> OrganizationConfig | None:
        """Get the default organization configuration."""
        if self.default_organization:
            return self.get_organization(self.default_organization)
        if self.organizations:
            return self.organizations[0]
        return None

    def get_effective_jira_config(self, org_name: str | None = None) -> JiraConfig:
        """Get effective Jira configuration merging global and org settings."""
        org = None
        if org_name:
            org = self.get_organization(org_name)
        elif self.default_organization:
            org = self.get_default_organization()

        if org is None:
            return self.global_jira

        # Merge configurations with org taking precedence
        return JiraConfig(
            default_project_prefix=(org.jira.default_project_prefix or self.global_jira.default_project_prefix),
            base_url=org.jira.base_url or self.global_jira.base_url,
            email=org.jira.email or self.global_jira.email,
            api_token=org.jira.api_token or self.global_jira.api_token,
            timeout_seconds=(
                org.jira.timeout_seconds if org.jira.timeout_seconds != 30 else self.global_jira.timeout_seconds
            ),
            max_retries=(org.jira.max_retries if org.jira.max_retries != 3 else self.global_jira.max_retries),
        )

    def get_effective_github_config(self, org_name: str | None = None) -> GitHubConfig:
        """Get effective GitHub configuration merging global and org settings."""
        org = None
        if org_name:
            org = self.get_organization(org_name)
        elif self.default_organization:
            org = self.get_default_organization()

        if org is None:
            return self.global_github

        # Merge configurations with org taking precedence
        return GitHubConfig(
            default_org=org.github.default_org or self.global_github.default_org,
            timeout_seconds=(
                org.github.timeout_seconds if org.github.timeout_seconds != 30 else self.global_github.timeout_seconds
            ),
            max_retries=(org.github.max_retries if org.github.max_retries != 3 else self.global_github.max_retries),
            use_ssh=org.github.use_ssh or self.global_github.use_ssh,
        )


# -----------------------------
# Configuration Loading Functions
# -----------------------------


def get_config_paths() -> tuple[Path, ...]:
    """Get possible configuration file paths in order of precedence.

    Follows XDG Base Directory specification for Linux systems.

    Returns:
        Tuple of Path objects in order of precedence (highest first):
        1. DEVHUB_CONFIG environment variable (absolute path to config file)
        2. Current directory .devhub.json
        3. $XDG_CONFIG_HOME/devhub/config.json (default: ~/.config/devhub/config.json)
        4. Each directory in $XDG_CONFIG_DIRS/devhub/config.json (default: /etc/xdg/devhub/config.json)
    """
    paths: list[Path] = []

    # 1. DEVHUB_CONFIG environment variable override
    if devhub_config := os.getenv("DEVHUB_CONFIG"):
        paths.append(Path(devhub_config))

    # 2. Project-local configuration
    paths.append(Path.cwd() / ".devhub.json")

    # 3. XDG_CONFIG_HOME (default: ~/.config/devhub/config.json)
    xdg_config_home = os.getenv("XDG_CONFIG_HOME")
    if xdg_config_home:
        paths.append(Path(xdg_config_home) / "devhub" / "config.json")
    else:
        paths.append(Path.home() / ".config" / "devhub" / "config.json")

    # 4. XDG_CONFIG_DIRS (default: /etc/xdg)
    xdg_config_dirs = os.getenv("XDG_CONFIG_DIRS", "/etc/xdg")
    paths.extend(
        Path(config_dir.strip()) / "devhub" / "config.json"
        for config_dir in xdg_config_dirs.split(":")
        if config_dir.strip()  # Skip empty strings
    )

    return tuple(paths)


def load_config_file(path: Path) -> Result[dict[str, Any], str]:
    """Load configuration from a JSON file.

    Args:
        path: Path to the configuration file

    Returns:
        Result containing the parsed JSON data or error message
    """
    try:
        if not path.exists():
            return Failure(f"Configuration file not found: {path}")

        if not path.is_file():
            return Failure(f"Path is not a file: {path}")

        content = path.read_text(encoding="utf-8")
        data = json.loads(content)

        if not isinstance(data, dict):
            return Failure(f"Configuration must be a JSON object, got {type(data).__name__}")

        return Success(cast("dict[str, Any]", data))

    except json.JSONDecodeError as e:
        return Failure(f"Invalid JSON in {path}: {e}")
    except OSError as e:
        return Failure(f"Failed to read {path}: {e}")


def parse_jira_config(data: dict[str, Any]) -> JiraConfig:
    """Parse Jira configuration from dictionary data."""
    return JiraConfig(
        default_project_prefix=data.get("default_project_prefix"),
        base_url=data.get("base_url"),
        email=data.get("email"),
        api_token=data.get("api_token"),
        timeout_seconds=data.get("timeout_seconds", 30),
        max_retries=data.get("max_retries", 3),
    )


def parse_github_config(data: dict[str, Any]) -> GitHubConfig:
    """Parse GitHub configuration from dictionary data."""
    return GitHubConfig(
        default_org=data.get("default_org"),
        timeout_seconds=data.get("timeout_seconds", 30),
        max_retries=data.get("max_retries", 3),
        use_ssh=data.get("use_ssh", False),
    )


def parse_output_config(data: dict[str, Any]) -> OutputConfig:
    """Parse output configuration from dictionary data."""
    return OutputConfig(
        base_directory=data.get("base_directory", "review-bundles"),
        include_timestamps=data.get("include_timestamps", True),
        file_permissions=data.get("file_permissions", 0o644),
        directory_permissions=data.get("directory_permissions", 0o755),
    )


def parse_bundle_defaults(data: dict[str, Any]) -> BundleDefaults:
    """Parse bundle defaults from dictionary data."""
    return BundleDefaults(
        include_jira=data.get("include_jira", True),
        include_pr=data.get("include_pr", True),
        include_diff=data.get("include_diff", True),
        include_comments=data.get("include_comments", True),
        comment_limit=data.get("comment_limit", 10),
        diff_context_lines=data.get("diff_context_lines", 3),
    )


def parse_organization_config(name: str, data: dict[str, Any]) -> OrganizationConfig:
    """Parse organization configuration from dictionary data."""
    return OrganizationConfig(
        name=name,
        jira=parse_jira_config(data.get("jira", {})),
        github=parse_github_config(data.get("github", {})),
        output=parse_output_config(data.get("output", {})),
        bundle_defaults=parse_bundle_defaults(data.get("bundle_defaults", {})),
        description=data.get("description"),
    )


def parse_config_data(data: dict[str, Any]) -> Result[DevHubConfig, str]:
    """Parse complete configuration from dictionary data.

    Args:
        data: Dictionary containing configuration data

    Returns:
        Result containing DevHubConfig or error message
    """
    try:
        # Parse organizations
        orgs_data = data.get("organizations", {})

        # Handle both list and dict formats for organizations
        if isinstance(orgs_data, list):
            # List format: [{"name": "org1", ...}, {"name": "org2", ...}]
            organizations = tuple(parse_organization_config(org_data["name"], org_data) for org_data in orgs_data)
        else:
            # Dict format: {"org1": {...}, "org2": {...}}
            organizations = tuple(parse_organization_config(name, org_data) for name, org_data in orgs_data.items())

        # Validate default organization exists
        default_org = data.get("default_organization")
        if default_org and not any(org.name == default_org for org in organizations):
            return Failure(f"Default organization '{default_org}' not found in organizations")

        config = DevHubConfig(
            default_organization=default_org,
            organizations=organizations,
            global_jira=parse_jira_config(data.get("jira", {})),
            global_github=parse_github_config(data.get("github", {})),
            global_output=parse_output_config(data.get("output", {})),
            config_version=data.get("config_version", "1.0"),
        )

        return Success(config)

    except Exception as e:
        return Failure(f"Failed to parse configuration: {e}")


def load_config() -> Result[DevHubConfig, str]:
    """Load DevHub configuration from available sources.

    Searches for configuration files in order of precedence and loads
    the first one found. Falls back to default configuration if none found.

    Returns:
        Result containing DevHubConfig or error message
    """
    config_paths = get_config_paths()

    for path in config_paths:
        result = load_config_file(path)
        if isinstance(result, Success):
            return parse_config_data(result.unwrap())

    # No configuration file found, return default
    return Success(DevHubConfig())


def load_config_with_environment(config_path: str | os.PathLike[str] | None = None) -> Result[DevHubConfig, str]:
    """Load configuration and merge with environment variables.

    This combines file-based configuration with environment variables,
    allowing for flexible deployment scenarios.

    Args:
        config_path: Optional path to config file

    Returns:
        Result containing DevHubConfig with environment overrides (never Failure)
    """
    # Determine base configuration
    base_config: DevHubConfig
    if config_path:
        try:
            result = load_config_file(Path(config_path))
            if isinstance(result, Failure):
                base_config = DevHubConfig()
            else:
                parsed = parse_config_data(result.unwrap())
                base_config = parsed.unwrap() if isinstance(parsed, Success) else DevHubConfig()
        except Exception:
            base_config = DevHubConfig()
    else:
        cfg_result = load_config()
        base_config = cfg_result.unwrap() if isinstance(cfg_result, Success) else DevHubConfig()

    # Helpers to parse optional integer env vars safely
    def _get_int_env(name: str) -> int | None:
        val = os.getenv(name)
        if val is None:
            return None
        try:
            return int(val)
        except ValueError:
            return None

    # Create environment-based Jira config
    env_jira = JiraConfig(
        base_url=os.getenv("JIRA_BASE_URL") or base_config.global_jira.base_url,
        email=os.getenv("JIRA_EMAIL") or base_config.global_jira.email,
        api_token=os.getenv("JIRA_API_TOKEN") or base_config.global_jira.api_token,
        default_project_prefix=(os.getenv("JIRA_DEFAULT_PROJECT") or base_config.global_jira.default_project_prefix),
        timeout_seconds=_get_int_env("JIRA_TIMEOUT_SECONDS") or base_config.global_jira.timeout_seconds,
        max_retries=base_config.global_jira.max_retries,
    )

    # Create environment-based GitHub config
    env_github = GitHubConfig(
        default_org=os.getenv("GITHUB_DEFAULT_ORG") or base_config.global_github.default_org,
        timeout_seconds=_get_int_env("GITHUB_TIMEOUT_SECONDS") or base_config.global_github.timeout_seconds,
        max_retries=base_config.global_github.max_retries,
        use_ssh=base_config.global_github.use_ssh,
    )

    # Optional default org override
    default_org_override = os.getenv("DEVHUB_ORGANIZATION") or base_config.default_organization

    # Optional output override
    output_dir_override = os.getenv("BUNDLE_OUTPUT_DIR")
    env_output = (
        OutputConfig(
            base_directory=output_dir_override,
            include_timestamps=base_config.global_output.include_timestamps,
            file_permissions=base_config.global_output.file_permissions,
            directory_permissions=base_config.global_output.directory_permissions,
        )
        if output_dir_override
        else base_config.global_output
    )

    # Create updated configuration
    updated_config = DevHubConfig(
        default_organization=default_org_override,
        organizations=base_config.organizations,
        global_jira=env_jira,
        global_github=env_github,
        global_output=env_output,
        config_version=base_config.config_version,
    )

    return Success(updated_config)


def create_example_config() -> DevHubConfig:
    """Create an example configuration for documentation purposes."""
    example_orgs = (
        OrganizationConfig(
            name="acme-corp",
            description="ACME Corporation development team",
            jira=JiraConfig(
                default_project_prefix="ACME",
                base_url="https://acme.atlassian.net",
                timeout_seconds=45,
            ),
            github=GitHubConfig(
                default_org="acme-corp",
                use_ssh=True,
            ),
            output=OutputConfig(
                base_directory="acme-reviews",
            ),
            bundle_defaults=BundleDefaults(
                comment_limit=15,
                diff_context_lines=5,
            ),
        ),
        OrganizationConfig(
            name="startup-inc",
            description="Startup Inc team settings",
            jira=JiraConfig(
                default_project_prefix="STARTUP",
                timeout_seconds=60,
            ),
            github=GitHubConfig(
                default_org="startup-inc",
            ),
            bundle_defaults=BundleDefaults(
                comment_limit=20,
            ),
        ),
    )

    return DevHubConfig(
        default_organization="acme-corp",
        organizations=example_orgs,
        global_jira=JiraConfig(
            timeout_seconds=30,
            max_retries=3,
        ),
        global_github=GitHubConfig(
            timeout_seconds=30,
        ),
        config_version="1.0",
    )


def export_config_to_dict(config: DevHubConfig) -> dict[str, Any]:
    """Export DevHub configuration to dictionary format.

    Useful for serializing configuration back to JSON format.

    Args:
        config: DevHubConfig to export

    Returns:
        Dictionary representation of the configuration
    """

    def jira_to_dict(jira: JiraConfig) -> dict[str, Any]:
        return {
            "default_project_prefix": jira.default_project_prefix,
            "base_url": jira.base_url,
            "email": jira.email,
            "api_token": jira.api_token,
            "timeout_seconds": jira.timeout_seconds,
            "max_retries": jira.max_retries,
        }

    def github_to_dict(github: GitHubConfig) -> dict[str, Any]:
        return {
            "default_org": github.default_org,
            "timeout_seconds": github.timeout_seconds,
            "max_retries": github.max_retries,
            "use_ssh": github.use_ssh,
        }

    def output_to_dict(output: OutputConfig) -> dict[str, Any]:
        return {
            "base_directory": output.base_directory,
            "include_timestamps": output.include_timestamps,
            "file_permissions": output.file_permissions,
            "directory_permissions": output.directory_permissions,
        }

    def bundle_to_dict(bundle: BundleDefaults) -> dict[str, Any]:
        return {
            "include_jira": bundle.include_jira,
            "include_pr": bundle.include_pr,
            "include_diff": bundle.include_diff,
            "include_comments": bundle.include_comments,
            "comment_limit": bundle.comment_limit,
            "diff_context_lines": bundle.diff_context_lines,
        }

    organizations = {
        org.name: {
            "description": org.description,
            "jira": jira_to_dict(org.jira),
            "github": github_to_dict(org.github),
            "output": output_to_dict(org.output),
            "bundle_defaults": bundle_to_dict(org.bundle_defaults),
        }
        for org in config.organizations
    }

    return {
        "config_version": config.config_version,
        "default_organization": config.default_organization,
        "organizations": organizations,
        "jira": jira_to_dict(config.global_jira),
        "github": github_to_dict(config.global_github),
        "output": output_to_dict(config.global_output),
    }
