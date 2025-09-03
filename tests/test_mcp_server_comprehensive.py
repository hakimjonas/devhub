"""Comprehensive tests for DevHub MCP Server module."""

import json
from typing import Any
from typing import cast
from unittest.mock import AsyncMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from returns.result import Failure
from returns.result import Success

from devhub.config import DevHubConfig
from devhub.main import JiraCredentials
from devhub.main import JiraIssue
from devhub.main import Repository
from devhub.main import ReviewComment
from devhub.mcp_server import DevHubMCPServer
from devhub.mcp_server import _print_available_tools
from devhub.mcp_server import _test_branch_context
from devhub.mcp_server import _test_configuration_loading
from devhub.mcp_server import _test_mcp_server
from devhub.mcp_server import _test_tools_listing
from devhub.mcp_server import cli_main
from devhub.mcp_server import main


class TestDevHubMCPServer:
    """Test DevHubMCPServer class."""

    def test_init(self):
        """Test server initialization."""
        server = DevHubMCPServer()

        assert isinstance(server.tools, dict)
        assert "get-bundle-context" in server.tools
        assert "get-jira-issue" in server.tools
        assert "get-pr-details" in server.tools
        assert "get-pr-comments" in server.tools
        assert "get-current-branch-context" in server.tools

        # Verify tool structure
        bundle_tool = cast("dict[str, Any]", server.tools["get-bundle-context"])
        assert "description" in bundle_tool
        assert "inputSchema" in bundle_tool
        assert bundle_tool["inputSchema"]["type"] == "object"
        assert "properties" in bundle_tool["inputSchema"]

    @pytest.mark.asyncio
    async def test_handle_request_initialize(self):
        """Test initialize request handling."""
        server = DevHubMCPServer()
        request = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}

        response = await server.handle_request(request)

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "result" in response
        assert response["result"]["protocolVersion"] == "2024-11-05"
        assert "capabilities" in response["result"]
        assert "serverInfo" in response["result"]
        assert response["result"]["serverInfo"]["name"] == "devhub-mcp-server"

    @pytest.mark.asyncio
    async def test_handle_request_tools_list(self):
        """Test tools/list request handling."""
        server = DevHubMCPServer()
        request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}

        response = await server.handle_request(request)

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 2
        assert "result" in response
        assert "tools" in response["result"]
        assert len(response["result"]["tools"]) == 5

        # Check tool structure
        tools = response["result"]["tools"]
        tool_names = [tool["name"] for tool in tools]
        assert "get-bundle-context" in tool_names
        assert "get-jira-issue" in tool_names

    @pytest.mark.asyncio
    async def test_handle_request_tool_call_get_bundle_context(self):
        """Test tools/call for get-bundle-context."""
        server = DevHubMCPServer()

        mock_bundle_data = {
            "jira": {"key": "TEST-123", "summary": "Test issue"},
            "pull_request": {"number": 456, "title": "Test PR"},
            "metadata": {"repository": {"owner": "test", "name": "repo"}},
        }

        with patch.object(server, "_get_bundle_context") as mock_get_bundle:
            mock_get_bundle.return_value = mock_bundle_data

            request = {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "get-bundle-context", "arguments": {"jira_key": "TEST-123", "pr_number": 456}},
            }

            response = await server.handle_request(request)

            assert response["jsonrpc"] == "2.0"
            assert response["id"] == 3
            assert "result" in response
            assert "content" in response["result"]
            assert len(response["result"]["content"]) == 1
            assert response["result"]["content"][0]["type"] == "text"

            # Verify the JSON content
            content_text = response["result"]["content"][0]["text"]
            parsed_content = json.loads(content_text)
            assert parsed_content["jira"]["key"] == "TEST-123"

    @pytest.mark.asyncio
    async def test_handle_request_tool_call_get_jira_issue(self):
        """Test tools/call for get-jira-issue."""
        server = DevHubMCPServer()

        mock_issue_data = {"key": "TEST-123", "summary": "Test issue", "description": "Test description"}

        with patch.object(server, "_get_jira_issue") as mock_get_jira:
            mock_get_jira.return_value = mock_issue_data

            request = {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "get-jira-issue", "arguments": {"jira_key": "TEST-123"}},
            }

            response = await server.handle_request(request)

            assert response["jsonrpc"] == "2.0"
            assert response["id"] == 4
            assert "result" in response

            content_text = response["result"]["content"][0]["text"]
            parsed_content = json.loads(content_text)
            assert parsed_content["key"] == "TEST-123"

    @pytest.mark.asyncio
    async def test_handle_request_tool_call_unknown_tool(self):
        """Test tools/call with unknown tool."""
        server = DevHubMCPServer()

        request = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "unknown-tool", "arguments": {}},
        }

        response = await server.handle_request(request)

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 5
        assert "error" in response
        assert response["error"]["code"] == -32602
        assert "Unknown tool" in response["error"]["message"]

    @pytest.mark.asyncio
    async def test_handle_request_unknown_method(self):
        """Test handling of unknown method."""
        server = DevHubMCPServer()

        request = {"jsonrpc": "2.0", "id": 6, "method": "unknown/method"}

        response = await server.handle_request(request)

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 6
        assert "error" in response
        assert response["error"]["code"] == -32601
        assert "Method not found" in response["error"]["message"]

    @pytest.mark.asyncio
    async def test_handle_request_invalid_method_type(self):
        """Test handling of invalid method type."""
        server = DevHubMCPServer()

        request = {"jsonrpc": "2.0", "id": 7, "method": 123}  # Invalid method type

        response = await server.handle_request(request)

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 7
        assert "error" in response
        assert response["error"]["code"] == -32601

    @pytest.mark.asyncio
    async def test_handle_request_exception(self):
        """Test exception handling in request processing."""
        server = DevHubMCPServer()

        with patch.object(server, "_handle_initialize") as mock_init:
            mock_init.side_effect = ValueError("Test error")

            request = {"jsonrpc": "2.0", "id": 8, "method": "initialize"}

            response = await server.handle_request(request)

            assert response["jsonrpc"] == "2.0"
            assert response["id"] == 8
            assert "error" in response
            assert response["error"]["code"] == -32603
            assert "Internal error" in response["error"]["message"]

    @pytest.mark.asyncio
    async def test_handle_tool_call_exception(self):
        """Test exception handling in tool call."""
        server = DevHubMCPServer()

        with patch.object(server, "_get_bundle_context") as mock_get_bundle:
            mock_get_bundle.side_effect = RuntimeError("Bundle error")

            request = {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {"name": "get-bundle-context", "arguments": {}},
            }

            response = await server.handle_request(request)

            assert response["jsonrpc"] == "2.0"
            assert response["id"] == 9
            assert "error" in response
            assert response["error"]["code"] == -32603
            assert "Tool execution error" in response["error"]["message"]

    def test_build_bundle_config_from_kwargs_defaults(self):
        """Test bundle config creation with defaults."""
        server = DevHubMCPServer()

        config = server._build_bundle_config_from_kwargs({})

        assert config.include_jira is True
        assert config.include_pr is True
        assert config.include_diff is True
        assert config.include_comments is True
        assert config.limit == 20

    def test_build_bundle_config_from_kwargs_custom(self):
        """Test bundle config creation with custom values."""
        server = DevHubMCPServer()

        kwargs = {"include_diff": False, "include_comments": False, "comment_limit": 50}

        config = server._build_bundle_config_from_kwargs(kwargs)

        assert config.include_jira is True
        assert config.include_pr is True
        assert config.include_diff is False
        assert config.include_comments is False
        assert config.limit == 50

    def test_build_bundle_config_from_kwargs_none_values(self):
        """Test bundle config creation with None values."""
        server = DevHubMCPServer()

        kwargs = {"include_diff": None, "include_comments": None, "comment_limit": None}

        config = server._build_bundle_config_from_kwargs(kwargs)

        assert config.include_diff is True  # Should default to True when None
        assert config.include_comments is True
        assert config.limit == 20

    def test_build_bundle_config_from_kwargs_string_limit(self):
        """Test bundle config creation with string comment_limit."""
        server = DevHubMCPServer()
        config = server._build_bundle_config_from_kwargs({"comment_limit": "30"})
        assert config.limit == 30

    def test_parse_identifiers_with_values(self):
        """Test identifier parsing with provided values."""
        server = DevHubMCPServer()

        kwargs = {"jira_key": "TEST-123", "pr_number": 456}
        jira_key, pr_number = server._parse_identifiers(kwargs)

        assert jira_key == "TEST-123"
        assert pr_number == 456

    def test_parse_identifiers_none_values(self):
        """Test identifier parsing with None values."""
        server = DevHubMCPServer()

        kwargs = {"jira_key": None, "pr_number": None}
        jira_key, pr_number = server._parse_identifiers(kwargs)

        assert jira_key is None
        assert pr_number is None

    def test_parse_identifiers_string_pr_number(self):
        """Test identifier parsing with string PR number."""
        server = DevHubMCPServer()

        kwargs = {"pr_number": "123"}
        jira_key, pr_number = server._parse_identifiers(kwargs)

        assert jira_key is None
        assert pr_number == 123

    def test_parse_identifiers_invalid_pr_number(self):
        """Test identifier parsing with invalid PR number."""
        server = DevHubMCPServer()

        kwargs = {"pr_number": "invalid"}
        jira_key, pr_number = server._parse_identifiers(kwargs)

        assert jira_key is None
        assert pr_number is None

    def test_parse_identifiers_numeric_jira_key(self):
        """Test identifier parsing coerces jira_key to string."""
        server = DevHubMCPServer()
        jira_key, pr_number = server._parse_identifiers({"jira_key": 123, "pr_number": None})
        assert jira_key == "123"
        assert pr_number is None

    def test_get_repo_and_branch_success(self):
        """Test successful repo and branch retrieval."""
        server = DevHubMCPServer()

        mock_repo = Repository(owner="test", name="repo")

        with (
            patch("devhub.mcp_server.get_repository_info") as mock_get_repo,
            patch("devhub.mcp_server.get_current_branch") as mock_get_branch,
        ):
            mock_get_repo.return_value = Success(mock_repo)
            mock_get_branch.return_value = Success("main")

            repo, branch = server._get_repo_and_branch()

            assert repo == mock_repo
            assert branch == "main"

    def test_get_repo_and_branch_repo_failure(self):
        """Test repo and branch retrieval with repo failure."""
        server = DevHubMCPServer()

        with patch("devhub.mcp_server.get_repository_info") as mock_get_repo:
            mock_get_repo.return_value = Failure("Repo error")

            with pytest.raises(TypeError, match="Failed to get repository info"):
                server._get_repo_and_branch()

    def test_get_repo_and_branch_branch_failure(self):
        """Test repo and branch retrieval with branch failure."""
        server = DevHubMCPServer()

        mock_repo = Repository(owner="test", name="repo")

        with (
            patch("devhub.mcp_server.get_repository_info") as mock_get_repo,
            patch("devhub.mcp_server.get_current_branch") as mock_get_branch,
        ):
            mock_get_repo.return_value = Success(mock_repo)
            mock_get_branch.return_value = Failure("Branch error")

            with pytest.raises(TypeError, match="Failed to get current branch"):
                server._get_repo_and_branch()

    def test_resolve_identifiers_with_existing_values(self):
        """Test identifier resolution with existing values."""
        server = DevHubMCPServer()

        config = DevHubConfig()
        repo = Repository(owner="test", name="repo")

        jira_key, pr_number = server._resolve_identifiers(config, repo, "main", "TEST-123", 456)

        assert jira_key == "TEST-123"
        assert pr_number == 456

    def test_resolve_identifiers_auto_resolve_jira(self):
        """Test identifier resolution with auto-resolving Jira key."""
        server = DevHubMCPServer()

        config = DevHubConfig()
        repo = Repository(owner="test", name="repo")

        with patch("devhub.mcp_server.resolve_jira_key_with_config") as mock_resolve:
            mock_resolve.return_value = "RESOLVED-123"

            jira_key, pr_number = server._resolve_identifiers(config, repo, "feature/test", None, 456)

            assert jira_key == "RESOLVED-123"
            assert pr_number == 456

    def test_resolve_identifiers_auto_resolve_pr(self):
        """Test identifier resolution with auto-resolving PR number."""
        server = DevHubMCPServer()

        config = DevHubConfig()
        repo = Repository(owner="test", name="repo")

        with patch("devhub.mcp_server.resolve_pr_number") as mock_resolve:
            mock_resolve.return_value = Success(789)

            jira_key, pr_number = server._resolve_identifiers(config, repo, "main", "TEST-123", None)

            assert jira_key == "TEST-123"
            assert pr_number == 789

    def test_resolve_identifiers_pr_resolution_failure(self):
        """Test identifier resolution with PR resolution failure."""
        server = DevHubMCPServer()

        config = DevHubConfig()
        repo = Repository(owner="test", name="repo")

        with patch("devhub.mcp_server.resolve_pr_number") as mock_resolve:
            mock_resolve.return_value = Failure("PR not found")

            jira_key, pr_number = server._resolve_identifiers(config, repo, "main", "TEST-123", None)

            assert jira_key == "TEST-123"
            assert pr_number is None

    @pytest.mark.asyncio
    async def test_get_bundle_context_success(self):
        """Test successful bundle context retrieval."""
        server = DevHubMCPServer()

        mock_repo = Repository(owner="test", name="repo")
        mock_bundle_result = '{"jira": {"key": "TEST-123"}, "metadata": {}}'

        with (
            patch("devhub.mcp_server.load_config_with_environment") as mock_load_config,
            patch.object(server, "_get_repo_and_branch") as mock_get_repo_branch,
            patch("devhub.mcp_server._gather_bundle_data") as mock_gather,
        ):
            mock_load_config.return_value = Success(DevHubConfig())
            mock_get_repo_branch.return_value = (mock_repo, "main")
            mock_gather.return_value = Success(mock_bundle_result)

            result = await server._get_bundle_context(jira_key="TEST-123", pr_number=456)

            assert result["jira"]["key"] == "TEST-123"

    @pytest.mark.asyncio
    async def test_get_bundle_context_gather_failure(self):
        """Test bundle context retrieval with gather failure."""
        server = DevHubMCPServer()

        mock_repo = Repository(owner="test", name="repo")

        with (
            patch("devhub.mcp_server.load_config_with_environment") as mock_load_config,
            patch.object(server, "_get_repo_and_branch") as mock_get_repo_branch,
            patch("devhub.mcp_server._gather_bundle_data") as mock_gather,
        ):
            mock_load_config.return_value = Success(DevHubConfig())
            mock_get_repo_branch.return_value = (mock_repo, "main")
            mock_gather.return_value = Failure("Gather failed")

            with pytest.raises(TypeError, match="Failed to gather bundle data"):
                await server._get_bundle_context()

    @pytest.mark.asyncio
    async def test_get_jira_issue_success(self):
        """Test successful Jira issue retrieval."""
        server = DevHubMCPServer()

        mock_issue = JiraIssue(key="TEST-123", summary="Test issue", description="Test description", raw_data={})

        mock_credentials = JiraCredentials(
            base_url="https://test.atlassian.net", email="test@example.com", api_token="test-token"
        )

        with (
            patch("devhub.mcp_server.load_config_with_environment") as mock_load_config,
            patch("devhub.mcp_server.get_jira_credentials_from_config") as mock_get_config_creds,
            patch("devhub.mcp_server.fetch_jira_issue") as mock_fetch,
        ):
            mock_load_config.return_value = Success(DevHubConfig())
            mock_get_config_creds.return_value = mock_credentials
            mock_fetch.return_value = Success(mock_issue)

            result = await server._get_jira_issue("TEST-123")

            assert result["key"] == "TEST-123"
            assert result["summary"] == "Test issue"

    @pytest.mark.asyncio
    async def test_get_jira_issue_no_credentials(self):
        """Test Jira issue retrieval with no credentials."""
        server = DevHubMCPServer()

        with (
            patch("devhub.mcp_server.load_config_with_environment") as mock_load_config,
            patch("devhub.mcp_server.get_jira_credentials_from_config") as mock_get_config_creds,
            patch("devhub.mcp_server.get_jira_credentials") as mock_get_env_creds,
        ):
            mock_load_config.return_value = Success(DevHubConfig())
            mock_get_config_creds.return_value = None
            mock_get_env_creds.return_value = None

            with pytest.raises(RuntimeError, match="Jira credentials not configured"):
                await server._get_jira_issue("TEST-123")

    @pytest.mark.asyncio
    async def test_get_jira_issue_fetch_failure(self):
        """Test Jira issue retrieval with fetch failure."""
        server = DevHubMCPServer()

        mock_credentials = JiraCredentials(
            base_url="https://test.atlassian.net", email="test@example.com", api_token="test-token"
        )

        with (
            patch("devhub.mcp_server.load_config_with_environment") as mock_load_config,
            patch("devhub.mcp_server.get_jira_credentials_from_config") as mock_get_config_creds,
            patch("devhub.mcp_server.fetch_jira_issue") as mock_fetch,
        ):
            mock_load_config.return_value = Success(DevHubConfig())
            mock_get_config_creds.return_value = mock_credentials
            mock_fetch.return_value = Failure("Fetch failed")

            with pytest.raises(TypeError, match="Failed to fetch Jira issue"):
                await server._get_jira_issue("TEST-123")

    @pytest.mark.asyncio
    async def test_get_pr_details_success(self):
        """Test successful PR details retrieval."""
        server = DevHubMCPServer()

        mock_repo = Repository(owner="test", name="repo")
        mock_pr_data = {"number": 123, "title": "Test PR"}
        mock_diff = "test diff content"

        with (
            patch("devhub.mcp_server.get_repository_info") as mock_get_repo,
            patch("devhub.mcp_server.fetch_pr_details") as mock_fetch_pr,
            patch("devhub.mcp_server.fetch_pr_diff") as mock_fetch_diff,
        ):
            mock_get_repo.return_value = Success(mock_repo)
            mock_fetch_pr.return_value = Success(mock_pr_data.copy())
            mock_fetch_diff.return_value = Success(mock_diff)

            result = await server._get_pr_details(123, include_diff=True)

            assert result["number"] == 123
            assert result["title"] == "Test PR"
            assert result["diff"] == mock_diff

    @pytest.mark.asyncio
    async def test_get_pr_details_no_diff(self):
        """Test PR details retrieval without diff."""
        server = DevHubMCPServer()

        mock_repo = Repository(owner="test", name="repo")
        mock_pr_data = {"number": 123, "title": "Test PR"}

        with (
            patch("devhub.mcp_server.get_repository_info") as mock_get_repo,
            patch("devhub.mcp_server.fetch_pr_details") as mock_fetch_pr,
        ):
            mock_get_repo.return_value = Success(mock_repo)
            mock_fetch_pr.return_value = Success(mock_pr_data)

            result = await server._get_pr_details(123, include_diff=False)

            assert result["number"] == 123
            assert result["title"] == "Test PR"
            assert "diff" not in result

    @pytest.mark.asyncio
    async def test_get_pr_details_repo_failure(self):
        """Test PR details retrieval with repository failure."""
        server = DevHubMCPServer()

        with patch("devhub.mcp_server.get_repository_info") as mock_get_repo:
            mock_get_repo.return_value = Failure("Repo error")

            with pytest.raises(TypeError, match="Failed to get repository info"):
                await server._get_pr_details(123)

    @pytest.mark.asyncio
    async def test_get_pr_details_fetch_failure(self):
        """Test PR details retrieval with fetch failure."""
        server = DevHubMCPServer()

        mock_repo = Repository(owner="test", name="repo")

        with (
            patch("devhub.mcp_server.get_repository_info") as mock_get_repo,
            patch("devhub.mcp_server.fetch_pr_details") as mock_fetch_pr,
        ):
            mock_get_repo.return_value = Success(mock_repo)
            mock_fetch_pr.return_value = Failure("Fetch failed")

            with pytest.raises(TypeError, match="Failed to fetch PR details"):
                await server._get_pr_details(123)

    @pytest.mark.asyncio
    async def test_get_pr_comments_success(self):
        """Test successful PR comments retrieval."""
        server = DevHubMCPServer()

        mock_repo = Repository(owner="test", name="repo")
        mock_comments = (
            ReviewComment(
                id="comment1",
                body="Test comment",
                path="test.py",
                author="reviewer",
                created_at="2024-01-01T00:00:00Z",
                diff_hunk="@@ -1,3 +1,3 @@",
                resolved=False,
            ),
        )

        with (
            patch("devhub.mcp_server.get_repository_info") as mock_get_repo,
            patch("devhub.mcp_server.fetch_unresolved_comments") as mock_fetch_comments,
        ):
            mock_get_repo.return_value = Success(mock_repo)
            mock_fetch_comments.return_value = Success(mock_comments)

            result = await server._get_pr_comments(123, limit=20)

            assert result["pr_number"] == 123
            assert result["total_comments"] == 1
            assert len(result["comments"]) == 1
            assert result["comments"][0]["body"] == "Test comment"

    @pytest.mark.asyncio
    async def test_get_pr_comments_failure(self):
        """Test PR comments retrieval with failure."""
        server = DevHubMCPServer()

        mock_repo = Repository(owner="test", name="repo")

        with (
            patch("devhub.mcp_server.get_repository_info") as mock_get_repo,
            patch("devhub.mcp_server.fetch_unresolved_comments") as mock_fetch_comments,
        ):
            mock_get_repo.return_value = Success(mock_repo)
            mock_fetch_comments.return_value = Failure("Fetch failed")

            with pytest.raises(TypeError, match="Failed to fetch comments"):
                await server._get_pr_comments(123)

    @pytest.mark.asyncio
    async def test_get_current_branch_context(self):
        """Test current branch context retrieval."""
        server = DevHubMCPServer()

        mock_bundle_data = {"jira": {"key": "TEST-123"}}

        with patch.object(server, "_get_bundle_context") as mock_get_bundle:
            mock_get_bundle.return_value = mock_bundle_data

            result = await server._get_current_branch_context(include_diff=False)

            assert result == mock_bundle_data
            mock_get_bundle.assert_called_once_with(include_diff=False)

    def test_error_response(self):
        """Test error response creation."""
        server = DevHubMCPServer()

        response = server._error_response("test-id", -32601, "Test error message")

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == "test-id"
        assert "error" in response
        assert response["error"]["code"] == -32601
        assert response["error"]["message"] == "Test error message"


class TestMCPServerUtilities:
    """Test MCP server utility functions."""

    @patch("builtins.print")
    def test_print_available_tools(self, mock_print):
        """Test printing available tools."""
        _print_available_tools()

        # Verify print was called multiple times (for different parts of output)
        assert mock_print.call_count > 5

        # Check that tool information was printed
        printed_text = " ".join(str(call.args[0]) for call in mock_print.call_args_list)
        assert "DevHub MCP Server - Available Tools" in printed_text
        assert "get-bundle-context" in printed_text
        assert "get-jira-issue" in printed_text

    @pytest.mark.asyncio
    @patch("builtins.print")
    async def test_test_tools_listing_success(self, mock_print):
        """Test tools listing test function."""
        server = DevHubMCPServer()

        await _test_tools_listing(server)

        # Verify success message was printed
        printed_text = " ".join(str(call.args[0]) for call in mock_print.call_args_list)
        assert "Tools available:" in printed_text

    @pytest.mark.asyncio
    @patch("builtins.print")
    async def test_test_tools_listing_failure(self, mock_print):
        """Test tools listing test function with failure."""
        server = DevHubMCPServer()

        with patch.object(server, "handle_request") as mock_handle:
            mock_handle.side_effect = ValueError("Test error")

            await _test_tools_listing(server)

            # Verify failure message was printed
            printed_text = " ".join(str(call.args[0]) for call in mock_print.call_args_list)
            assert "Tools test failed:" in printed_text

    @pytest.mark.asyncio
    @patch("builtins.print")
    async def test_test_branch_context_success(self, mock_print):
        """Test branch context test function."""
        server = DevHubMCPServer()

        mock_response = {"jsonrpc": "2.0", "id": 2, "result": {"content": []}}

        with patch.object(server, "handle_request") as mock_handle:
            mock_handle.return_value = mock_response

            await _test_branch_context(server)

            # Verify success message was printed
            printed_text = " ".join(str(call.args[0]) for call in mock_print.call_args_list)
            assert "Current branch context accessible" in printed_text

    @pytest.mark.asyncio
    @patch("builtins.print")
    async def test_test_branch_context_error(self, mock_print):
        """Test branch context test function with error response."""
        server = DevHubMCPServer()

        mock_response = {"jsonrpc": "2.0", "id": 2, "error": {"code": -32603, "message": "Test error"}}

        with patch.object(server, "handle_request") as mock_handle:
            mock_handle.return_value = mock_response

            await _test_branch_context(server)

            # Verify warning message was printed
            printed_text = " ".join(str(call.args[0]) for call in mock_print.call_args_list)
            assert "Branch context: Test error" in printed_text

    @pytest.mark.asyncio
    @patch("builtins.print")
    async def test_test_configuration_loading_success(self, mock_print):
        """Test configuration loading test function."""
        with patch("devhub.mcp_server.load_config_with_environment") as mock_load:
            mock_load.return_value = Success(DevHubConfig())

            await _test_configuration_loading()

            # Verify success message was printed
            printed_text = " ".join(str(call.args[0]) for call in mock_print.call_args_list)
            assert "Configuration loaded successfully" in printed_text

    @pytest.mark.asyncio
    @patch("builtins.print")
    async def test_test_configuration_loading_failure(self, mock_print):
        """Test configuration loading test function with failure."""
        with patch("devhub.mcp_server.load_config_with_environment") as mock_load:
            mock_load.return_value = Failure("Config error")

            await _test_configuration_loading()

            # Verify warning message was printed
            printed_text = " ".join(str(call.args[0]) for call in mock_print.call_args_list)
            assert "Configuration: Config error" in printed_text

    @pytest.mark.asyncio
    @patch("builtins.print")
    async def test_test_mcp_server(self, mock_print):
        """Test MCP server test function."""
        with (
            patch("devhub.mcp_server._test_tools_listing") as mock_test_tools,
            patch("devhub.mcp_server._test_branch_context") as mock_test_branch,
            patch("devhub.mcp_server._test_configuration_loading") as mock_test_config,
        ):
            await _test_mcp_server()

            # Verify all test functions were called
            mock_test_tools.assert_called_once()
            mock_test_branch.assert_called_once()
            mock_test_config.assert_called_once()

            # Verify test output was printed
            printed_text = " ".join(str(call.args[0]) for call in mock_print.call_args_list)
            assert "Testing DevHub MCP Server" in printed_text
            assert "MCP server test completed" in printed_text


class TestMCPServerMain:
    """Test MCP server main function and CLI."""

    @pytest.mark.asyncio
    async def test_main_function_normal_operation(self):
        """Test main function normal operation."""
        mock_request = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
        mock_response = {"jsonrpc": "2.0", "id": 1, "result": {}}

        # Mock stdin to return request then empty line to break loop
        mock_stdin_lines = [json.dumps(mock_request), ""]

        with (
            patch("sys.stdin") as mock_stdin,
            patch("builtins.print") as mock_print,
            patch("asyncio.get_event_loop") as mock_get_loop,
        ):
            # Setup readline to return lines then empty string to break loop
            mock_stdin.readline.side_effect = mock_stdin_lines

            with patch("devhub.mcp_server_comprehensive.asyncio.create_task") as mock_create_task:
                # Fix the coroutine call - asyncio doesn't have a 'coroutine' attribute
                # Instead, we'll mock the task creation directly
                mock_task = Mock()
                mock_create_task.return_value = mock_task

                # Mock the event loop
                mock_loop = Mock()
                mock_loop.run_in_executor = AsyncMock(side_effect=mock_stdin_lines)
                mock_get_loop.return_value = mock_loop

                # Mock server response
                with patch("devhub.mcp_server.DevHubMCPServer") as mock_server_class:
                    mock_server = Mock()
                    mock_server.handle_request = AsyncMock(return_value=mock_response)
                    mock_server_class.return_value = mock_server

                    await main()

                    # Verify server was called correctly
                    mock_server.handle_request.assert_called_once_with(mock_request)
                    mock_print.assert_called_with(json.dumps(mock_response), flush=True)

    @pytest.mark.asyncio
    async def test_main_function_exception_handling(self):
        """Test main function exception handling."""
        with (
            patch("sys.stdin") as mock_stdin,
            patch("builtins.print") as mock_print,
            patch("asyncio.get_event_loop") as mock_get_loop,
        ):
            # Setup mocks to cause exception then empty string to break loop
            mock_stdin.readline.side_effect = ["invalid json", ""]

            # Mock the event loop
            mock_loop = Mock()
            mock_loop.run_in_executor = AsyncMock(side_effect=["invalid json", ""])
            mock_get_loop.return_value = mock_loop

            await main()

            # Verify error response was printed
            assert mock_print.called
            printed_calls = [str(call.args[0]) for call in mock_print.call_args_list]
            # Should contain an error response
            error_found = any("error" in call for call in printed_calls)
            assert error_found

    def test_cli_main_tools_option(self):
        """Test CLI main with --tools option."""
        with (
            patch("sys.argv", ["devhub-mcp", "--tools"]),
            patch("devhub.mcp_server._print_available_tools") as mock_print_tools,
        ):
            cli_main()

            mock_print_tools.assert_called_once()

    def test_cli_main_test_option(self):
        """Test CLI main with --test option."""
        with patch("sys.argv", ["devhub-mcp", "--test"]), patch("asyncio.run") as mock_asyncio_run:
            cli_main()

            mock_asyncio_run.assert_called_once()

    def test_cli_main_version_option(self):
        """Test CLI main with --version option."""
        with patch("sys.argv", ["devhub-mcp", "--version"]), pytest.raises(SystemExit):
            cli_main()

    def test_cli_main_server_mode(self):
        """Test CLI main in server mode (default)."""
        with (
            patch("sys.argv", ["devhub-mcp"]),
            patch("logging.basicConfig") as mock_logging,
            patch("asyncio.run") as mock_asyncio_run,
        ):
            cli_main()

            mock_logging.assert_called_once()
            mock_asyncio_run.assert_called_once()

    def test_cli_main_explicit_server_mode(self):
        """Test CLI main with explicit --server option."""
        with (
            patch("sys.argv", ["devhub-mcp", "--server"]),
            patch("logging.basicConfig") as mock_logging,
            patch("asyncio.run") as mock_asyncio_run,
        ):
            cli_main()

            mock_logging.assert_called_once()
            mock_asyncio_run.assert_called_once()
