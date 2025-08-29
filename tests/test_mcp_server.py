"""Unit tests for DevHubMCPServer focusing on dispatch and tool behaviors.

These tests mock external dependencies to avoid network/CLI calls and to keep them fast.
"""

import json
from typing import Any
from unittest.mock import Mock
from unittest.mock import patch

from returns.result import Success

from devhub.config import DevHubConfig
from devhub.main import JiraCredentials
from devhub.main import JiraIssue
from devhub.main import Repository
from devhub.main import ReviewComment
from devhub.mcp_server import DevHubMCPServer


def _mk_response_content(result: dict[str, Any]) -> dict[str, Any]:
    """Helper to build expected MCP content wrapper."""
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(result, indent=2, ensure_ascii=False),
            }
        ]
    }


def test_initialize_and_tools_list() -> None:
    """Validate initialize and tools/list responses include expected fields."""
    server = DevHubMCPServer()

    # Actual initialize call
    init_resp = (
        __import__("asyncio")
        .get_event_loop()
        .run_until_complete(server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"}))
    )
    assert init_resp["id"] == 1
    assert "result" in init_resp
    assert "protocolVersion" in init_resp["result"]

    tools_resp = (
        __import__("asyncio")
        .get_event_loop()
        .run_until_complete(server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}))
    )
    assert tools_resp["id"] == 2
    tools = tools_resp["result"]["tools"]
    names = {t["name"] for t in tools}
    assert "get-bundle-context" in names
    assert "get-jira-issue" in names
    assert "get-pr-details" in names
    assert "get-pr-comments" in names


def test_handle_unknown_method() -> None:
    """Return method-not-found error for unknown JSON-RPC method."""
    server = DevHubMCPServer()
    resp = (
        __import__("asyncio")
        .get_event_loop()
        .run_until_complete(server.handle_request({"jsonrpc": "2.0", "id": 3, "method": "nope"}))
    )
    assert resp["id"] == 3
    assert resp["error"]["code"] == -32601


@patch("devhub.mcp_server._gather_bundle_data")
@patch("devhub.mcp_server.resolve_pr_number")
@patch("devhub.mcp_server.get_current_branch")
@patch("devhub.mcp_server.get_repository_info")
@patch("devhub.mcp_server.load_config_with_environment")
def test_get_bundle_context_happy(
    mock_load_config: Mock,
    mock_repo_info: Mock,
    mock_branch: Mock,
    mock_resolve_pr: Mock,
    mock_gather: Mock,
) -> None:
    """Happy path for get-bundle-context tool call."""
    server = DevHubMCPServer()

    mock_load_config.return_value = Success(DevHubConfig())
    mock_repo_info.return_value = Success(Repository(owner="acme", name="proj"))
    mock_branch.return_value = Success("feat/ACME-42-cool")
    mock_resolve_pr.return_value = Success(42)
    mock_gather.return_value = Success(json.dumps({"ok": True}))

    req = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "get-bundle-context",
            "arguments": {"include_diff": True, "include_comments": True, "comment_limit": 5},
        },
    }

    resp = __import__("asyncio").get_event_loop().run_until_complete(server.handle_request(req))
    assert resp["id"] == 4
    assert "result" in resp
    content = resp["result"]["content"][0]["text"]
    payload = json.loads(content)
    assert payload == {"ok": True}


def test_tools_call_unknown_tool() -> None:
    """Return invalid-params error for unknown tool name."""
    server = DevHubMCPServer()

    req = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {"name": "no-tool", "arguments": {}},
    }
    resp = __import__("asyncio").get_event_loop().run_until_complete(server.handle_request(req))
    assert resp["id"] == 5
    assert resp["error"]["code"] == -32602


@patch("devhub.mcp_server.fetch_jira_issue")
@patch("devhub.mcp_server.get_jira_credentials_from_config")
@patch("devhub.mcp_server.load_config_with_environment")
def test_get_jira_issue_happy(mock_load_config: Mock, mock_get_creds_cfg: Mock, mock_fetch: Mock) -> None:
    """Happy path for fetching a Jira issue via tool call."""
    server = DevHubMCPServer()

    mock_load_config.return_value = Success(DevHubConfig())
    creds = JiraCredentials(base_url="https://example", email="a@b.com", api_token="x")
    mock_get_creds_cfg.return_value = creds
    mock_fetch.return_value = Success(JiraIssue(key="ACME-1", summary="s", description="d", raw_data={}))

    req = {
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {"name": "get-jira-issue", "arguments": {"jira_key": "ACME-1"}},
    }
    resp = __import__("asyncio").get_event_loop().run_until_complete(server.handle_request(req))
    assert resp["id"] == 6
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["key"] == "ACME-1"


@patch("devhub.mcp_server.fetch_pr_diff")
@patch("devhub.mcp_server.fetch_pr_details")
@patch("devhub.mcp_server.get_repository_info")
def test_get_pr_details_with_diff(mock_repo: Mock, mock_details: Mock, mock_diff: Mock) -> None:
    """Happy path for fetching PR details including diff content."""
    server = DevHubMCPServer()

    mock_repo.return_value = Success(Repository(owner="acme", name="proj"))
    mock_details.return_value = Success({"id": 123, "title": "PR"})
    mock_diff.return_value = Success("DIFF")

    req = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {"name": "get-pr-details", "arguments": {"pr_number": 123, "include_diff": True}},
    }
    resp = __import__("asyncio").get_event_loop().run_until_complete(server.handle_request(req))
    assert resp["id"] == 7
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["id"] == 123
    assert payload["diff"] == "DIFF"


@patch("devhub.mcp_server.fetch_unresolved_comments")
@patch("devhub.mcp_server.get_repository_info")
def test_get_pr_comments(mock_repo: Mock, mock_comments: Mock) -> None:
    """Happy path for fetching unresolved PR comments list."""
    server = DevHubMCPServer()

    mock_repo.return_value = Success(Repository(owner="acme", name="proj"))
    c1 = ReviewComment(
        id="1",
        body="b1",
        path="p.py",
        author="u",
        created_at="t",
        diff_hunk="h",
        resolved=False,
    )
    mock_comments.return_value = Success((c1,))

    req = {
        "jsonrpc": "2.0",
        "id": 8,
        "method": "tools/call",
        "params": {"name": "get-pr-comments", "arguments": {"pr_number": 7, "limit": 1}},
    }
    resp = __import__("asyncio").get_event_loop().run_until_complete(server.handle_request(req))
    assert resp["id"] == 8
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["pr_number"] == 7
    assert payload["total_comments"] == 1
    assert payload["comments"][0]["id"] == "1"


@patch("devhub.mcp_server.fetch_pr_details", side_effect=RuntimeError("boom"))
@patch("devhub.mcp_server.get_repository_info")
def test_tool_call_exception_is_caught(mock_repo: Mock, mock_repo_unused: Mock) -> None:
    """Return internal-error when a tool implementation raises unexpectedly."""
    server = DevHubMCPServer()
    mock_repo.return_value = Success(Repository(owner="acme", name="proj"))

    req = {
        "jsonrpc": "2.0",
        "id": 9,
        "method": "tools/call",
        "params": {"name": "get-pr-details", "arguments": {"pr_number": 1}},
    }
    resp = __import__("asyncio").get_event_loop().run_until_complete(server.handle_request(req))
    assert resp["id"] == 9
    assert resp["error"]["code"] == -32603
