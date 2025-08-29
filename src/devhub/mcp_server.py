"""DevHub MCP (Model Context Protocol) Server implementation.

This module provides a standardized MCP server that allows AI agents to interact
with DevHub functionality through structured tools and resources.
"""

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Awaitable
from collections.abc import Callable
from dataclasses import asdict
from typing import Any
from typing import cast

from returns.result import Success

from devhub.config import DevHubConfig
from devhub.config import load_config_with_environment
from devhub.main import BundleConfig
from devhub.main import Repository
from devhub.main import _gather_bundle_data
from devhub.main import fetch_jira_issue
from devhub.main import fetch_pr_details
from devhub.main import fetch_pr_diff
from devhub.main import fetch_unresolved_comments
from devhub.main import get_current_branch
from devhub.main import get_jira_credentials
from devhub.main import get_jira_credentials_from_config
from devhub.main import get_repository_info
from devhub.main import resolve_jira_key_with_config
from devhub.main import resolve_pr_number


logger = logging.getLogger(__name__)


class DevHubMCPServer:
    """MCP Server for DevHub integration with AI agents."""

    def __init__(self) -> None:
        """Initialize the MCP server with available tools."""
        self.tools = {
            "get-bundle-context": {
                "description": "Get comprehensive bundle with Jira issue, PR details, diff, and comments",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "jira_key": {"type": "string", "description": "Jira issue key (e.g., PROJ-123)"},
                        "pr_number": {"type": "integer", "description": "GitHub PR number"},
                        "include_diff": {"type": "boolean", "description": "Include PR diff", "default": True},
                        "include_comments": {
                            "type": "boolean",
                            "description": "Include review comments",
                            "default": True,
                        },
                        "comment_limit": {"type": "integer", "description": "Max comments to include", "default": 20},
                    },
                },
            },
            "get-jira-issue": {
                "description": "Fetch specific Jira issue details",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "jira_key": {"type": "string", "description": "Jira issue key (e.g., PROJ-123)"},
                    },
                    "required": ["jira_key"],
                },
            },
            "get-pr-details": {
                "description": "Fetch GitHub PR information",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "pr_number": {"type": "integer", "description": "GitHub PR number"},
                        "include_diff": {"type": "boolean", "description": "Include PR diff", "default": True},
                    },
                    "required": ["pr_number"],
                },
            },
            "get-pr-comments": {
                "description": "Fetch unresolved PR review comments",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "pr_number": {"type": "integer", "description": "GitHub PR number"},
                        "limit": {"type": "integer", "description": "Max comments to fetch", "default": 20},
                    },
                    "required": ["pr_number"],
                },
            },
            "get-current-branch-context": {
                "description": "Get context for current git branch (auto-detects Jira key and PR)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "include_diff": {"type": "boolean", "description": "Include PR diff", "default": True},
                        "include_comments": {
                            "type": "boolean",
                            "description": "Include review comments",
                            "default": True,
                        },
                        "comment_limit": {"type": "integer", "description": "Max comments to include", "default": 20},
                    },
                },
            },
        }

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle incoming MCP requests."""
        try:
            method = request.get("method")
            params = request.get("params", {})
            request_id = request.get("id")

            if not isinstance(method, str):
                return self._error_response(request_id, -32601, f"Method not found: {method!r}")

            # Dispatch table for method handling
            method_handlers: dict[str, Callable[[], Awaitable[dict[str, Any]]]] = {
                "initialize": lambda: self._handle_initialize(request_id),
                "tools/list": lambda: self._handle_tools_list(request_id),
                "tools/call": lambda: self._handle_tool_call(
                    request_id, params.get("name", ""), params.get("arguments", {})
                ),
            }

            handler = method_handlers.get(method)
            if handler:
                return await handler()

            return self._error_response(request_id, -32601, f"Method not found: {method}")

        except Exception as e:
            logger.exception("Error handling MCP request")
            return self._error_response(request.get("id"), -32603, f"Internal error: {e}")

    async def _handle_initialize(self, request_id: int | str | None) -> dict[str, Any]:
        """Handle MCP initialize request."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                },
                "serverInfo": {
                    "name": "devhub-mcp-server",
                    "version": "1.0.0",
                },
            },
        }

    async def _handle_tools_list(self, request_id: int | str | None) -> dict[str, Any]:
        """Handle tools/list request."""
        tools = [
            {
                "name": name,
                "description": tool["description"],
                "inputSchema": tool["inputSchema"],
            }
            for name, tool in self.tools.items()
        ]

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": tools,
            },
        }

    async def _handle_tool_call(
        self, request_id: int | str | None, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle tools/call request."""
        try:
            if tool_name == "get-bundle-context":
                result = await self._get_bundle_context(**arguments)
            elif tool_name == "get-jira-issue":
                result = await self._get_jira_issue(**arguments)
            elif tool_name == "get-pr-details":
                result = await self._get_pr_details(**arguments)
            elif tool_name == "get-pr-comments":
                result = await self._get_pr_comments(**arguments)
            elif tool_name == "get-current-branch-context":
                result = await self._get_current_branch_context(**arguments)
            else:
                return self._error_response(request_id, -32602, f"Unknown tool: {tool_name}")

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, indent=2, ensure_ascii=False),
                        }
                    ],
                },
            }

        except Exception as e:
            logger.exception("Error calling tool %s", tool_name)
            return self._error_response(request_id, -32603, f"Tool execution error: {e}")

    # ---- Internal helpers -------------------------------------------------

    @staticmethod
    def _build_bundle_config_from_kwargs(kwargs: dict[str, Any]) -> BundleConfig:
        """Create BundleConfig from loosely-typed kwargs safely."""
        include_diff_val = kwargs.get("include_diff", True)
        include_diff = bool(include_diff_val) if include_diff_val is not None else True

        include_comments_val = kwargs.get("include_comments", True)
        include_comments = bool(include_comments_val) if include_comments_val is not None else True

        comment_limit_val = kwargs.get("comment_limit", 20)
        comment_limit = int(comment_limit_val) if isinstance(comment_limit_val, (int, str)) else 20

        return BundleConfig(
            include_jira=True,
            include_pr=True,
            include_diff=include_diff,
            include_comments=include_comments,
            limit=comment_limit,
        )

    @staticmethod
    def _parse_identifiers(kwargs: dict[str, Any]) -> tuple[str | None, int | None]:
        """Parse jira_key and pr_number from kwargs without auto-resolution."""
        jira_key_val = kwargs.get("jira_key")
        jira_key = str(jira_key_val) if jira_key_val is not None else None

        pr_number_val = kwargs.get("pr_number")
        pr_number = int(pr_number_val) if isinstance(pr_number_val, (int, str)) else None
        return jira_key, pr_number

    @staticmethod
    def _get_repo_and_branch() -> tuple[Repository, str]:
        """Get repository info and current branch or raise TypeError on failure."""
        repo_result = get_repository_info()
        if not isinstance(repo_result, Success):
            error_msg = f"Failed to get repository info: {repo_result.failure()}"
            raise TypeError(error_msg)
        repo = repo_result.unwrap()

        branch_result = get_current_branch()
        if not isinstance(branch_result, Success):
            error_msg = f"Failed to get current branch: {branch_result.failure()}"
            raise TypeError(error_msg)
        branch = branch_result.unwrap()
        return repo, branch

    @staticmethod
    def _resolve_identifiers(
        devhub_config: DevHubConfig,
        repo: Repository,
        branch: str,
        jira_key: str | None,
        pr_number: int | None,
    ) -> tuple[str | None, int | None]:
        """Auto-resolve missing jira_key and pr_number using repo/branch context."""
        if not jira_key:
            jira_key = resolve_jira_key_with_config(devhub_config, branch=branch)
        if not pr_number:
            pr_result = resolve_pr_number(repo, None, branch, jira_key)
            if isinstance(pr_result, Success):
                pr_number = pr_result.unwrap()
        return jira_key, pr_number

    # ---- Tool implementations --------------------------------------------

    async def _get_bundle_context(self, **kwargs: str | int | bool | None) -> dict[str, Any]:
        """Get comprehensive bundle context."""
        # Load configuration
        config_result = load_config_with_environment()
        devhub_config = config_result.unwrap() if isinstance(config_result, Success) else DevHubConfig()

        # Prepare config and context
        bundle_config = self._build_bundle_config_from_kwargs(cast("dict[str, Any]", kwargs))
        repo, branch = self._get_repo_and_branch()

        # Parse and resolve identifiers
        jira_key, pr_number = self._parse_identifiers(cast("dict[str, Any]", kwargs))
        jira_key, pr_number = self._resolve_identifiers(devhub_config, repo, branch, jira_key, pr_number)

        # Gather and return bundle data
        args = argparse.Namespace(metadata_only=False, format="json")
        result = _gather_bundle_data(args, bundle_config, repo, branch, jira_key, pr_number, devhub_config)
        if not isinstance(result, Success):
            error_msg = f"Failed to gather bundle data: {result.failure()}"
            raise TypeError(error_msg)

        return cast("dict[str, Any]", json.loads(result.unwrap()))

    async def _get_jira_issue(self, jira_key: str) -> dict[str, Any]:
        """Get Jira issue details."""
        # Load configuration and get credentials
        config_result = load_config_with_environment()
        devhub_config = config_result.unwrap() if isinstance(config_result, Success) else None

        credentials = None
        if devhub_config:
            credentials = get_jira_credentials_from_config(devhub_config, None)
        if not credentials:
            credentials = get_jira_credentials()

        if not credentials:
            error_msg = "Jira credentials not configured"
            raise RuntimeError(error_msg)

        # Fetch issue
        result = fetch_jira_issue(credentials, jira_key)
        if not isinstance(result, Success):
            error_msg = f"Failed to fetch Jira issue: {result.failure()}"
            raise TypeError(error_msg)

        issue = result.unwrap()
        return asdict(issue)

    async def _get_pr_details(self, pr_number: int, include_diff: bool = True) -> dict[str, Any]:
        """Get PR details."""
        # Get repository info
        repo_result = get_repository_info()
        if not isinstance(repo_result, Success):
            error_msg = f"Failed to get repository info: {repo_result.failure()}"
            raise TypeError(error_msg)
        repo = repo_result.unwrap()

        # Fetch PR details
        pr_result = fetch_pr_details(repo, pr_number)
        if not isinstance(pr_result, Success):
            error_msg = f"Failed to fetch PR details: {pr_result.failure()}"
            raise TypeError(error_msg)

        pr_data = pr_result.unwrap()

        if include_diff:
            diff_result = fetch_pr_diff(pr_number)
            if isinstance(diff_result, Success):
                pr_data["diff"] = diff_result.unwrap()

        return cast("dict[str, Any]", pr_data)

    async def _get_pr_comments(self, pr_number: int, limit: int = 20) -> dict[str, Any]:
        """Get PR review comments."""
        # Get repository info
        repo_result = get_repository_info()
        if not isinstance(repo_result, Success):
            error_msg = f"Failed to get repository info: {repo_result.failure()}"
            raise TypeError(error_msg)
        repo = repo_result.unwrap()

        # Fetch comments
        comments_result = fetch_unresolved_comments(repo, pr_number, limit)
        if not isinstance(comments_result, Success):
            error_msg = f"Failed to fetch comments: {comments_result.failure()}"
            raise TypeError(error_msg)

        comments = comments_result.unwrap()
        return {
            "pr_number": pr_number,
            "comments": [asdict(comment) for comment in comments],
            "total_comments": len(comments),
        }

    async def _get_current_branch_context(self, **kwargs: str | int | bool | None) -> dict[str, Any]:
        """Get context for current branch with auto-detection."""
        return await self._get_bundle_context(**kwargs)

    def _error_response(self, request_id: int | str | None, code: int, message: str) -> dict[str, Any]:
        """Create error response."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message,
            },
        }


async def main() -> None:
    """Run the MCP server."""
    server = DevHubMCPServer()

    # Read from stdin and write to stdout for MCP communication
    while True:
        try:
            line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
            if not line:
                break

            request = json.loads(line.strip())
            response = await server.handle_request(request)

            print(json.dumps(response), flush=True)  # noqa: T201

        except Exception as e:
            logger.exception("Error in MCP server main loop")
            error_msg = f"Server error: {e}"
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32603,
                    "message": error_msg,
                },
            }
            print(json.dumps(error_response), flush=True)  # noqa: T201


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
