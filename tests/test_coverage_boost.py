"""Additional tests to improve code coverage."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from returns.result import Failure
from returns.result import Success

from devhub.config import DevHubConfig
from devhub.config import GitHubConfig
from devhub.config import JiraConfig
from devhub.config import OrganizationConfig
from devhub.main import BundleData
from devhub.main import Repository
from devhub.main import _write_bundle_json
from devhub.sdk import DevHubClient


class TestAdditionalConfigCoverage:
    """Additional tests to improve config coverage."""

    def test_get_effective_github_config_with_org(self):
        """Test get_effective_github_config with organization."""
        org_config = OrganizationConfig(
            name="test-org",
            github=GitHubConfig(default_org="custom-org", timeout_seconds=45),
        )
        config = DevHubConfig(
            organizations=(org_config,),  # Use tuple, not dict
            default_organization="test-org",
        )

        result = config.get_effective_github_config("test-org")
        assert result.default_org == "custom-org"
        assert result.timeout_seconds == 45

    def test_get_effective_github_config_default_values(self):
        """Test get_effective_github_config with default values that don't override."""
        org_config = OrganizationConfig(
            name="test-org",
            github=GitHubConfig(default_org=None, timeout_seconds=30),  # Default values
        )
        config = DevHubConfig(
            organizations=(org_config,),  # Use tuple, not dict
            global_github=GitHubConfig(default_org="global-org", timeout_seconds=60),
        )

        result = config.get_effective_github_config("test-org")
        assert result.default_org == "global-org"  # Should use global since org is None
        assert result.timeout_seconds == 60  # Should use global since org is default

    def test_get_effective_jira_config_default_values(self):
        """Test get_effective_jira_config with default values that don't override."""
        org_config = OrganizationConfig(
            name="test-org",
            jira=JiraConfig(
                base_url=None,
                email=None,
                api_token=None,
                max_retries=3,  # Default value
            ),
        )
        config = DevHubConfig(
            organizations=(org_config,),  # Use tuple, not dict
            global_jira=JiraConfig(
                base_url="https://global.atlassian.net",
                email="global@test.com",
                api_token="global-token",
                max_retries=5,
            ),
        )

        result = config.get_effective_jira_config("test-org")
        assert result.base_url == "https://global.atlassian.net"
        assert result.email == "global@test.com"
        assert result.api_token == "global-token"
        assert result.max_retries == 5  # Should use global since org is default


class TestAdditionalMainCoverage:
    """Additional tests to improve main module coverage."""

    def test_write_bundle_json_callable_bundle_json_path(self):
        """Test _write_bundle_json with callable bundle_json method."""
        from devhub.main import OutputPaths

        # Create a mock OutputPaths with callable bundle_json
        mock_output_paths = Mock(spec=OutputPaths)
        import tempfile as _tempfile  # local import to avoid global temp path usage

        _tmp_dir = _tempfile.mkdtemp()
        mock_bundle_json_path = Path(_tmp_dir) / "bundle.json"
        mock_output_paths.bundle_json = Mock(return_value=mock_bundle_json_path)

        with (
            patch("devhub.main.ensure_directory") as mock_ensure,
            patch("devhub.main.write_json_file") as mock_write,
            patch("json.loads") as mock_json_loads,
        ):
            mock_ensure.return_value = Success(None)
            mock_write.return_value = Success(None)
            mock_json_loads.return_value = {"test": "data"}

            result = _write_bundle_json('{"test": "data"}', mock_output_paths)

            assert isinstance(result, Success)
            mock_output_paths.bundle_json.assert_called_once()
            mock_ensure.assert_called_once_with(mock_bundle_json_path.parent)

    def test_write_bundle_json_invalid_base_dir(self):
        """Test _write_bundle_json with invalid base_dir."""
        mock_output_paths = Mock()
        mock_output_paths.bundle_json = None
        mock_output_paths.base_dir = None  # Invalid base_dir

        result = _write_bundle_json('{"test": "data"}', mock_output_paths)

        assert isinstance(result, Failure)
        assert "Invalid output paths: missing base directory" in result.failure()

    def test_bundle_data_to_dict_no_repository(self):
        """Test BundleData.to_dict with no repository."""
        bundle = BundleData(repository=None, branch="test-branch")
        result = bundle.to_dict()

        assert result["metadata"]["repository"] is None
        assert result["metadata"]["branch"] == "test-branch"


class TestAdditionalSDKCoverage:
    """Additional tests to improve SDK coverage."""

    def test_devhub_client_process_result_json_decode_error(self):
        """Test DevHubClient._process_result with JSON decode error."""
        client = DevHubClient()
        repo = Repository(owner="test", name="repo")

        from devhub.sdk import ContextRequest

        request = ContextRequest()

        # Invalid JSON string
        result = client._process_result("invalid json", repo, "main", request)

        assert isinstance(result, Failure)
        assert "Failed to process bundle data" in result.failure()

    @pytest.mark.asyncio
    async def test_devhub_client_execute_cli_command_return_code_error(self):
        """Test DevHubClient.execute_cli_command with non-zero return code."""
        client = DevHubClient()

        with patch("asyncio.create_subprocess_exec") as mock_create_process:
            mock_process = Mock()
            mock_process.returncode = 1
            mock_process.communicate.return_value = (b"stdout", b"stderr output")
            mock_create_process.return_value = mock_process

            with patch("asyncio.wait_for") as mock_wait:
                mock_wait.return_value = (b"stdout", b"stderr output")

                result = await client.execute_cli_command(["test", "command"])

                assert isinstance(result, Failure)
                assert "CLI command failed: stderr output" in result.failure()


class TestConfigFileEdgeCases:
    """Test edge cases in config file handling."""

    def test_load_config_file_with_actual_file_operations(self):
        """Test loading config file with actual file operations for better coverage."""
        from devhub.config import load_config_file

        # Test with non-existent file
        result = load_config_file(Path("/nonexistent/path/config.json"))
        assert isinstance(result, Failure)
        assert "not found" in result.failure()

        # Test with actual file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config_data = {
                "organizations": {
                    "test-org": {
                        "name": "test-org",
                        "jira": {"base_url": "https://test.atlassian.net"},
                    }
                }
            }
            json.dump(config_data, f)
            f.flush()

            try:
                result = load_config_file(Path(f.name))
                assert isinstance(result, Success)
                # load_config_file returns raw dict, not DevHubConfig object
                config_dict = result.unwrap()
                assert "test-org" in config_dict["organizations"]
            finally:
                os.unlink(f.name)


class TestMainHelperFunctions:
    """Test helper functions in main module for better coverage."""

    def test_setup_bundle_config_all_options(self):
        """Test _setup_bundle_config with all options set."""
        import argparse

        from devhub.main import _setup_bundle_config

        args = argparse.Namespace()
        args.config = "/custom/config.json"
        args.organization = "test-org"
        args.no_jira = True
        args.no_pr = True
        args.no_diff = True
        args.no_comments = True
        args.limit = 50

        with patch("devhub.main.load_config_with_environment") as mock_load:
            mock_load.return_value = Failure("Config load failed")

            devhub_config, bundle_config = _setup_bundle_config(args)

            # Should use default config when loading fails
            assert isinstance(devhub_config, DevHubConfig)
            assert bundle_config.include_jira is False
            assert bundle_config.include_pr is False
            assert bundle_config.include_diff is False
            assert bundle_config.include_comments is False
            assert bundle_config.limit == 50
            assert bundle_config.organization == "test-org"

    def test_resolve_identifiers_explicit_values_provided(self):
        """Test _resolve_identifiers when explicit values are provided."""
        import argparse

        from devhub.main import _resolve_identifiers

        args = argparse.Namespace()
        args.jira_key = "EXPLICIT-123"
        args.pr_number = 456
        args.organization = "test-org"

        devhub_config = DevHubConfig()
        repo = Repository(owner="test", name="repo")

        with (
            patch("devhub.main.resolve_jira_key_with_config") as mock_resolve_jira,
            patch("devhub.main.resolve_pr_number") as mock_resolve_pr,
        ):
            # resolve_jira_key_with_config should return the explicit key since it has priority
            mock_resolve_jira.return_value = "EXPLICIT-123"
            mock_resolve_pr.return_value = Success(456)

            result = _resolve_identifiers(args, devhub_config, repo, "main")

            assert isinstance(result, Success)
            jira_key, pr_number = result.unwrap()
            assert jira_key == "EXPLICIT-123"
            assert pr_number == 456

            # These should be called since the functions handle the priority logic internally
            mock_resolve_jira.assert_called_once_with(
                devhub_config, branch="main", explicit_key="EXPLICIT-123", org_name="test-org"
            )
            mock_resolve_pr.assert_called_once_with(repo, 456, "main", "EXPLICIT-123")
