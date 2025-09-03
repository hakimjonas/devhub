"""Additional config tests for edge cases and merging behavior."""

import os
from unittest.mock import patch

from returns.result import Failure
from returns.result import Success

from devhub.config import DevHubConfig
from devhub.config import GitHubConfig
from devhub.config import OrganizationConfig
from devhub.config import load_config_with_environment
from devhub.config import parse_config_data


def test_effective_github_config_merging():
    global_gh = GitHubConfig(default_org="glob", timeout_seconds=60, max_retries=9, use_ssh=True)
    # Org sets default_org and leaves timeouts at sentinel values to inherit
    org = OrganizationConfig(
        name="x", github=GitHubConfig(default_org="org", timeout_seconds=30, max_retries=3, use_ssh=False)
    )
    cfg = DevHubConfig(default_organization="x", organizations=(org,), global_github=global_gh)

    eff = cfg.get_effective_github_config()
    assert eff.default_org == "org"  # org precedence
    # Sentinel 30 -> inherit from global
    assert eff.timeout_seconds == 60
    # Sentinel 3 -> inherit from global
    assert eff.max_retries == 9
    # use_ssh uses org or global (boolean or)
    assert eff.use_ssh is True


@patch.dict(os.environ, {"JIRA_BASE_URL": "https://env.example", "GITHUB_DEFAULT_ORG": "env-org"}, clear=True)
@patch("devhub.config.load_config_file")
def test_load_config_with_environment_path_failure(mock_load_file):
    mock_load_file.return_value = Failure("not found")
    res = load_config_with_environment(config_path="/nope/config.json")
    assert isinstance(res, Success)
    cfg = res.unwrap()
    # Should fall back to defaults, but apply env overrides
    assert cfg.global_jira.base_url == "https://env.example"
    assert cfg.global_github.default_org == "env-org"


@patch.dict(os.environ, {"JIRA_EMAIL": "env@example.com"}, clear=True)
@patch("devhub.config.load_config_file")
@patch("devhub.config.parse_config_data")
def test_load_config_with_environment_path_parse_failure(mock_parse, mock_load_file):
    mock_load_file.return_value = Success({})
    mock_parse.return_value = Failure("bad config")
    res = load_config_with_environment(config_path="/tmp/config.json")
    assert isinstance(res, Success)
    cfg = res.unwrap()
    assert cfg.global_jira.email == "env@example.com"


def test_parse_config_data_invalid_organizations_type():
    # organizations must be a mapping; list should fail
    data = {"organizations": ["not", "a", "dict"]}
    res = parse_config_data(data)
    assert isinstance(res, Failure)
    assert "Failed to parse configuration" in res.failure()
