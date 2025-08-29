"""Tests for DevHub configuration system."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given
from hypothesis import strategies as st
from returns.result import Failure
from returns.result import Success

from devhub.config import BundleDefaults
from devhub.config import DevHubConfig
from devhub.config import GitHubConfig
from devhub.config import JiraConfig
from devhub.config import OrganizationConfig
from devhub.config import OutputConfig
from devhub.config import create_example_config
from devhub.config import export_config_to_dict
from devhub.config import get_config_paths
from devhub.config import load_config
from devhub.config import load_config_file
from devhub.config import load_config_with_environment
from devhub.config import parse_config_data
from devhub.config import parse_jira_config
from devhub.config import parse_organization_config


class TestConfigDataStructures:
    """Tests for immutable configuration data structures."""

    def test_jira_config_defaults(self) -> None:
        """Test JiraConfig with default values."""
        config = JiraConfig()

        assert config.default_project_prefix is None
        assert config.base_url is None
        assert config.email is None
        assert config.api_token is None
        assert config.timeout_seconds == 30
        assert config.max_retries == 3

    def test_jira_config_custom(self) -> None:
        """Test JiraConfig with custom values."""
        config = JiraConfig(
            default_project_prefix="ACME",
            base_url="https://acme.atlassian.net",
            email="test@acme.com",
            api_token="token123",
            timeout_seconds=45,
            max_retries=5,
        )

        assert config.default_project_prefix == "ACME"
        assert config.base_url == "https://acme.atlassian.net"
        assert config.email == "test@acme.com"
        assert config.api_token == "token123"
        assert config.timeout_seconds == 45
        assert config.max_retries == 5

    def test_jira_config_immutable(self) -> None:
        """Test that JiraConfig is immutable."""
        config = JiraConfig(default_project_prefix="ACME")

        with pytest.raises((AttributeError, TypeError)):
            config.default_project_prefix = "OTHER"  # type: ignore[misc]

    def test_github_config_defaults(self) -> None:
        """Test GitHubConfig with default values."""
        config = GitHubConfig()

        assert config.default_org is None
        assert config.timeout_seconds == 30
        assert config.max_retries == 3
        assert config.use_ssh is False

    def test_output_config_defaults(self) -> None:
        """Test OutputConfig with default values."""
        config = OutputConfig()

        assert config.base_directory == "review-bundles"
        assert config.include_timestamps is True
        assert config.file_permissions == 0o644
        assert config.directory_permissions == 0o755

    def test_bundle_defaults_defaults(self) -> None:
        """Test BundleDefaults with default values."""
        config = BundleDefaults()

        assert config.include_jira is True
        assert config.include_pr is True
        assert config.include_diff is True
        assert config.include_comments is True
        assert config.comment_limit == 10
        assert config.diff_context_lines == 3

    def test_organization_config_defaults(self) -> None:
        """Test OrganizationConfig with default values."""
        config = OrganizationConfig(name="test-org")

        assert config.name == "test-org"
        assert isinstance(config.jira, JiraConfig)
        assert isinstance(config.github, GitHubConfig)
        assert isinstance(config.output, OutputConfig)
        assert isinstance(config.bundle_defaults, BundleDefaults)
        assert config.description is None

    def test_organization_config_custom(self) -> None:
        """Test OrganizationConfig with custom values."""
        jira_config = JiraConfig(default_project_prefix="ACME")
        config = OrganizationConfig(name="acme-corp", jira=jira_config, description="ACME Corporation")

        assert config.name == "acme-corp"
        assert config.jira.default_project_prefix == "ACME"
        assert config.description == "ACME Corporation"

    def test_devhub_config_defaults(self) -> None:
        """Test DevHubConfig with default values."""
        config = DevHubConfig()

        assert config.default_organization is None
        assert len(config.organizations) == 0
        assert isinstance(config.global_jira, JiraConfig)
        assert isinstance(config.global_github, GitHubConfig)
        assert isinstance(config.global_output, OutputConfig)
        assert config.config_version == "1.0"

    def test_devhub_config_get_organization(self) -> None:
        """Test getting organization by name."""
        org1 = OrganizationConfig(name="org1")
        org2 = OrganizationConfig(name="org2")
        config = DevHubConfig(organizations=(org1, org2))

        assert config.get_organization("org1") == org1
        assert config.get_organization("org2") == org2
        assert config.get_organization("nonexistent") is None

    def test_devhub_config_get_default_organization(self) -> None:
        """Test getting default organization."""
        org1 = OrganizationConfig(name="org1")
        org2 = OrganizationConfig(name="org2")

        # Test with explicit default
        config = DevHubConfig(default_organization="org2", organizations=(org1, org2))
        assert config.get_default_organization() == org2

        # Test with first org as default
        config = DevHubConfig(organizations=(org1, org2))
        assert config.get_default_organization() == org1

        # Test with no organizations
        config = DevHubConfig()
        assert config.get_default_organization() is None

    def test_devhub_config_effective_jira_config(self) -> None:
        """Test effective Jira configuration merging."""
        global_jira = JiraConfig(base_url="https://global.atlassian.net", timeout_seconds=30)

        org_jira = JiraConfig(default_project_prefix="ACME", base_url="https://acme.atlassian.net", timeout_seconds=45)

        org = OrganizationConfig(name="acme", jira=org_jira)
        config = DevHubConfig(default_organization="acme", organizations=(org,), global_jira=global_jira)

        effective = config.get_effective_jira_config()

        # Org settings should take precedence
        assert effective.default_project_prefix == "ACME"
        assert effective.base_url == "https://acme.atlassian.net"
        assert effective.timeout_seconds == 45

        # Global fallback for unset values
        # (email and api_token are None in both, so they remain None)
        assert effective.email is None
        assert effective.api_token is None

    @given(
        project_prefix=st.text(min_size=1, max_size=10),
        timeout=st.integers(min_value=1, max_value=300),
        max_retries=st.integers(min_value=1, max_value=10),
    )
    def test_jira_config_property_based(self, project_prefix: str, timeout: int, max_retries: int) -> None:
        """Property-based test for JiraConfig creation."""
        config = JiraConfig(
            default_project_prefix=project_prefix,
            timeout_seconds=timeout,
            max_retries=max_retries,
        )

        assert config.default_project_prefix == project_prefix
        assert config.timeout_seconds == timeout
        assert config.max_retries == max_retries

        # Immutability is already tested in test_jira_config_immutable


class TestConfigParsing:
    """Tests for configuration parsing functions."""

    def test_parse_jira_config_empty(self) -> None:
        """Test parsing Jira config from empty data."""
        config = parse_jira_config({})

        assert config.default_project_prefix is None
        assert config.base_url is None
        assert config.timeout_seconds == 30
        assert config.max_retries == 3

    def test_parse_jira_config_full(self) -> None:
        """Test parsing Jira config with all fields."""
        data = {
            "default_project_prefix": "ACME",
            "base_url": "https://acme.atlassian.net",
            "email": "test@acme.com",
            "api_token": "token123",
            "timeout_seconds": 45,
            "max_retries": 5,
        }

        config = parse_jira_config(data)

        assert config.default_project_prefix == "ACME"
        assert config.base_url == "https://acme.atlassian.net"
        assert config.email == "test@acme.com"
        assert config.api_token == "token123"
        assert config.timeout_seconds == 45
        assert config.max_retries == 5

    def test_parse_organization_config(self) -> None:
        """Test parsing organization configuration."""
        data = {
            "description": "Test Organization",
            "jira": {"default_project_prefix": "TEST", "base_url": "https://test.atlassian.net"},
            "github": {"default_org": "test-org", "use_ssh": True},
            "bundle_defaults": {"comment_limit": 20},
        }

        config = parse_organization_config("test-org", data)

        assert config.name == "test-org"
        assert config.description == "Test Organization"
        assert config.jira.default_project_prefix == "TEST"
        assert config.jira.base_url == "https://test.atlassian.net"
        assert config.github.default_org == "test-org"
        assert config.github.use_ssh is True
        assert config.bundle_defaults.comment_limit == 20

    def test_parse_config_data_success(self) -> None:
        """Test successful configuration data parsing."""
        data = {
            "config_version": "1.0",
            "default_organization": "acme",
            "organizations": {"acme": {"description": "ACME Corp", "jira": {"default_project_prefix": "ACME"}}},
            "jira": {"timeout_seconds": 60},
        }

        result = parse_config_data(data)

        assert isinstance(result, Success)
        config = result.unwrap()
        assert config.config_version == "1.0"
        assert config.default_organization == "acme"
        assert len(config.organizations) == 1
        assert config.organizations[0].name == "acme"
        assert config.organizations[0].jira.default_project_prefix == "ACME"
        assert config.global_jira.timeout_seconds == 60

    def test_parse_config_data_invalid_default_org(self) -> None:
        """Test parsing with invalid default organization."""
        data = {"default_organization": "nonexistent", "organizations": {"acme": {"description": "ACME Corp"}}}

        result = parse_config_data(data)

        assert isinstance(result, Failure)
        assert "Default organization 'nonexistent' not found" in result.failure()


class TestConfigFileOperations:
    """Tests for configuration file loading operations."""

    def test_get_config_paths_default(self) -> None:
        """Test getting configuration file paths with default XDG settings."""
        with patch.dict("os.environ", {}, clear=True):
            paths = get_config_paths()

            # Verify minimum expected paths
            assert len(paths) >= 3  # At least local and XDG paths

            # First path should be project-local (no DEVHUB_CONFIG set)
            assert paths[0] == Path.cwd() / ".devhub.json"

            # Should include XDG default paths
            assert Path.home() / ".config" / "devhub" / "config.json" in paths
            assert Path("/etc/xdg/devhub/config.json") in paths

    @patch.dict("os.environ", {"DEVHUB_CONFIG": "/custom/path/config.json"})
    def test_get_config_paths_with_devhub_config(self) -> None:
        """Test DEVHUB_CONFIG environment variable override."""
        paths = get_config_paths()

        # DEVHUB_CONFIG should be first path
        assert paths[0] == Path("/custom/path/config.json")
        # Other paths should still be present
        assert Path.cwd() / ".devhub.json" in paths

    @patch.dict("os.environ", {"XDG_CONFIG_HOME": "/custom/config"})
    def test_get_config_paths_with_xdg_config_home(self) -> None:
        """Test XDG_CONFIG_HOME environment variable."""
        paths = get_config_paths()

        # Should use custom XDG_CONFIG_HOME
        assert Path("/custom/config/devhub/config.json") in paths
        # Should not include default ~/.config path
        default_xdg_path = Path.home() / ".config" / "devhub" / "config.json"
        assert default_xdg_path not in paths

    @patch.dict("os.environ", {"XDG_CONFIG_DIRS": "/etc/xdg:/usr/local/etc:/opt/etc"})
    def test_get_config_paths_with_xdg_config_dirs(self) -> None:
        """Test XDG_CONFIG_DIRS with multiple directories."""
        paths = get_config_paths()

        # Should include all XDG_CONFIG_DIRS paths
        assert Path("/etc/xdg/devhub/config.json") in paths
        assert Path("/usr/local/etc/devhub/config.json") in paths
        assert Path("/opt/etc/devhub/config.json") in paths

    @patch.dict("os.environ", {"XDG_CONFIG_DIRS": "  /path1  :  /path2  :  "})
    def test_get_config_paths_with_xdg_config_dirs_whitespace(self) -> None:
        """Test XDG_CONFIG_DIRS with whitespace and empty entries."""
        paths = get_config_paths()

        # Should handle whitespace and empty entries correctly
        assert Path("/path1/devhub/config.json") in paths
        assert Path("/path2/devhub/config.json") in paths
        # Should not create paths for empty entries

    def test_get_config_paths_precedence_order(self) -> None:
        """Test complete precedence order with all environment variables set."""
        env_vars = {
            "DEVHUB_CONFIG": "/override/config.json",
            "XDG_CONFIG_HOME": "/custom/config",
            "XDG_CONFIG_DIRS": "/etc/xdg:/usr/local/etc",
        }

        with patch.dict("os.environ", env_vars):
            paths = get_config_paths()

            # Verify exact order based on specification
            expected_paths = [
                Path("/override/config.json"),  # DEVHUB_CONFIG
                Path.cwd() / ".devhub.json",  # Project local
                Path("/custom/config/devhub/config.json"),  # XDG_CONFIG_HOME
                Path("/etc/xdg/devhub/config.json"),  # XDG_CONFIG_DIRS[0]
                Path("/usr/local/etc/devhub/config.json"),  # XDG_CONFIG_DIRS[1]
            ]

            # Should match exactly in order
            assert len(paths) == len(expected_paths)
            for i, expected_path in enumerate(expected_paths):
                assert paths[i] == expected_path, f"Position {i}: expected {expected_path}, got {paths[i]}"

    def test_load_config_file_success(self) -> None:
        """Test successful config file loading."""
        config_data = {"config_version": "1.0", "jira": {"timeout_seconds": 45}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            f.flush()

            try:
                result = load_config_file(Path(f.name))

                assert isinstance(result, Success)
                data = result.unwrap()
                assert data["config_version"] == "1.0"
                assert data["jira"]["timeout_seconds"] == 45
            finally:
                os.unlink(f.name)

    def test_load_config_file_not_found(self) -> None:
        """Test loading non-existent config file."""
        result = load_config_file(Path("/nonexistent/config.json"))

        assert isinstance(result, Failure)
        assert "Configuration file not found" in result.failure()

    def test_load_config_file_invalid_json(self) -> None:
        """Test loading config file with invalid JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{ invalid json }")
            f.flush()

            try:
                result = load_config_file(Path(f.name))

                assert isinstance(result, Failure)
                assert "Invalid JSON" in result.failure()
            finally:
                os.unlink(f.name)

    def test_load_config_file_not_object(self) -> None:
        """Test loading config file that's not a JSON object."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(["not", "an", "object"], f)
            f.flush()

            try:
                result = load_config_file(Path(f.name))

                assert isinstance(result, Failure)
                assert "Configuration must be a JSON object" in result.failure()
            finally:
                os.unlink(f.name)

    @patch("devhub.config.get_config_paths")
    @patch("devhub.config.load_config_file")
    def test_load_config_found(self, mock_load_file, mock_get_paths) -> None:
        """Test loading config when file is found."""
        mock_paths = [Path("/test/config1.json"), Path("/test/config2.json")]
        mock_get_paths.return_value = mock_paths

        config_data = {"jira": {"timeout_seconds": 45}}
        mock_load_file.side_effect = [
            Failure("File not found"),  # First file fails
            Success(config_data),  # Second file succeeds
        ]

        result = load_config()

        assert isinstance(result, Success)
        config = result.unwrap()
        assert config.global_jira.timeout_seconds == 45

    @patch("devhub.config.get_config_paths")
    @patch("devhub.config.load_config_file")
    def test_load_config_not_found(self, mock_load_file, mock_get_paths) -> None:
        """Test loading config when no file is found."""
        mock_paths = [Path("/test/config.json")]
        mock_get_paths.return_value = mock_paths
        mock_load_file.return_value = Failure("File not found")

        result = load_config()

        # Should return default config when no file found
        assert isinstance(result, Success)
        config = result.unwrap()
        assert isinstance(config, DevHubConfig)
        assert config.global_jira.timeout_seconds == 30  # Default value


class TestEnvironmentIntegration:
    """Tests for environment variable integration."""

    @patch.dict(
        "os.environ",
        {
            "JIRA_BASE_URL": "https://env.atlassian.net",
            "JIRA_EMAIL": "env@example.com",
            "JIRA_API_TOKEN": "env-token",
            "JIRA_DEFAULT_PROJECT": "ENV",
            "GITHUB_DEFAULT_ORG": "env-org",
        },
    )
    @patch("devhub.config.load_config")
    def test_load_config_with_environment(self, mock_load_config) -> None:
        """Test loading config with environment variable overrides."""
        # Mock base config
        base_config = DevHubConfig(global_jira=JiraConfig(base_url="https://file.atlassian.net", timeout_seconds=60))
        mock_load_config.return_value = Success(base_config)

        result = load_config_with_environment()

        assert isinstance(result, Success)
        config = result.unwrap()

        # Environment variables should override file values
        assert config.global_jira.base_url == "https://env.atlassian.net"
        assert config.global_jira.email == "env@example.com"
        assert config.global_jira.api_token == "env-token"
        assert config.global_jira.default_project_prefix == "ENV"
        assert config.global_github.default_org == "env-org"

        # Non-overridden values should remain
        assert config.global_jira.timeout_seconds == 60

    @patch.dict("os.environ", {}, clear=True)
    @patch("devhub.config.load_config")
    def test_load_config_with_environment_no_env_vars(self, mock_load_config) -> None:
        """Test loading config with no environment variables."""
        base_config = DevHubConfig(global_jira=JiraConfig(base_url="https://file.atlassian.net"))
        mock_load_config.return_value = Success(base_config)

        result = load_config_with_environment()

        assert isinstance(result, Success)
        config = result.unwrap()

        # File values should be preserved
        assert config.global_jira.base_url == "https://file.atlassian.net"


class TestConfigUtilities:
    """Tests for configuration utility functions."""

    def test_create_example_config(self) -> None:
        """Test creating example configuration."""
        config = create_example_config()

        assert config.default_organization == "acme-corp"
        assert len(config.organizations) == 2

        acme = config.get_organization("acme-corp")
        assert acme is not None
        assert acme.jira.default_project_prefix == "ACME"
        assert acme.description == "ACME Corporation development team"

        startup = config.get_organization("startup-inc")
        assert startup is not None
        assert startup.jira.default_project_prefix == "STARTUP"

    def test_export_config_to_dict(self) -> None:
        """Test exporting configuration to dictionary."""
        config = DevHubConfig(
            config_version="1.0",
            default_organization="test",
            organizations=(
                OrganizationConfig(name="test", description="Test Org", jira=JiraConfig(default_project_prefix="TEST")),
            ),
            global_jira=JiraConfig(timeout_seconds=45),
        )

        result = export_config_to_dict(config)

        assert result["config_version"] == "1.0"
        assert result["default_organization"] == "test"
        assert "organizations" in result
        assert "test" in result["organizations"]
        assert result["organizations"]["test"]["description"] == "Test Org"
        assert result["organizations"]["test"]["jira"]["default_project_prefix"] == "TEST"
        assert result["jira"]["timeout_seconds"] == 45

    def test_config_roundtrip(self) -> None:
        """Test configuration export/import roundtrip."""
        original = create_example_config()

        # Export to dict
        exported = export_config_to_dict(original)

        # Parse back from dict
        result = parse_config_data(exported)

        assert isinstance(result, Success)
        imported = result.unwrap()

        # Should be equivalent
        assert imported.config_version == original.config_version
        assert imported.default_organization == original.default_organization
        assert len(imported.organizations) == len(original.organizations)

        # Check first organization
        orig_org = original.organizations[0]
        imp_org = imported.organizations[0]
        assert orig_org.name == imp_org.name
        assert orig_org.jira.default_project_prefix == imp_org.jira.default_project_prefix


class TestRealWorldScenarios:
    """Tests for real-world configuration scenarios."""

    def test_multi_organization_scenario(self) -> None:
        """Test configuration with multiple organizations."""
        config = DevHubConfig(
            default_organization="primary",
            organizations=(
                OrganizationConfig(
                    name="primary",
                    jira=JiraConfig(default_project_prefix="PRIM"),
                    bundle_defaults=BundleDefaults(comment_limit=15),
                ),
                OrganizationConfig(
                    name="secondary",
                    jira=JiraConfig(default_project_prefix="SEC"),
                    bundle_defaults=BundleDefaults(comment_limit=25),
                ),
            ),
        )

        # Default organization
        default_org = config.get_default_organization()
        assert default_org is not None
        assert default_org.name == "primary"

        # Effective configs
        primary_jira = config.get_effective_jira_config("primary")
        assert primary_jira.default_project_prefix == "PRIM"

        secondary_jira = config.get_effective_jira_config("secondary")
        assert secondary_jira.default_project_prefix == "SEC"

        # Non-existent organization should fall back to global
        nonexistent_jira = config.get_effective_jira_config("nonexistent")
        assert nonexistent_jira == config.global_jira

    def test_configuration_hierarchy(self) -> None:
        """Test configuration value hierarchy (org > global > default)."""
        config = DevHubConfig(
            global_jira=JiraConfig(base_url="https://global.atlassian.net", timeout_seconds=45, max_retries=5),
            organizations=(
                OrganizationConfig(
                    name="special",
                    jira=JiraConfig(
                        base_url="https://special.atlassian.net",
                        timeout_seconds=90,
                        # max_retries not specified, should inherit
                    ),
                ),
            ),
        )

        effective = config.get_effective_jira_config("special")

        # Org-specific values
        assert effective.base_url == "https://special.atlassian.net"
        assert effective.timeout_seconds == 90

        # Global fallback
        assert effective.max_retries == 5

        # Default fallback (None values)
        assert effective.email is None
