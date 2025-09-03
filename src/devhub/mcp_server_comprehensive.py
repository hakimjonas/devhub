"""Compatibility shim for comprehensive MCP server tests.

This module re-exports devhub.mcp_server and exposes the asyncio module,
so tests can patch `devhub.mcp_server_comprehensive.asyncio.create_task` safely.
"""

# Re-export all public symbols from the actual MCP server implementation
from .mcp_server import *  # noqa: F403
