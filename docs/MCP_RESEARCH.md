# MCP (Model Context Protocol) Research for DevHub Integration

## Overview

The Model Context Protocol (MCP) is a standardized way for AI agents to interact with external tools and services. This document outlines the research and implementation plan for creating a DevHub MCP server.

## MCP Protocol Basics

### Core Concepts
- **Server**: Provides tools and resources to AI clients
- **Client**: AI agent that consumes tools and resources
- **Tools**: Functions that clients can call to perform actions
- **Resources**: Data sources that clients can access

### Protocol Structure
```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "tool_name",
    "arguments": {}
  },
  "id": 1
}
```

## DevHub MCP Server Design

### Tools to Provide

1. **get-bundle-context**
   - Retrieve comprehensive bundle with Jira, PR, diff, comments
   - Parameters: jira_key?, pr_number?, include_diff?, include_comments?
   - Returns: Complete bundle data as JSON

2. **get-jira-issue**
   - Fetch specific Jira issue details
   - Parameters: jira_key
   - Returns: Jira issue data

3. **get-pr-details**
   - Fetch GitHub PR information
   - Parameters: pr_number, include_diff?
   - Returns: PR data with optional diff

4. **get-pr-comments**
   - Fetch unresolved PR review comments
   - Parameters: pr_number, limit?
   - Returns: Array of review comments

5. **analyze-code-changes**
   - Get code change impact analysis
   - Parameters: pr_number
   - Returns: Analysis summary

### Resources to Provide

1. **current-branch-context**
   - Auto-detected context for current branch
   - URI: devhub://current-branch

2. **project-configuration**
   - Current DevHub configuration
   - URI: devhub://config

### Implementation Architecture

```python
from typing import Any, Dict, List, Optional
import asyncio
import json

class DevHubMCPServer:
    def __init__(self):
        self.tools = {
            "get-bundle-context": self.get_bundle_context,
            "get-jira-issue": self.get_jira_issue,
            "get-pr-details": self.get_pr_details,
            "get-pr-comments": self.get_pr_comments,
        }
    
    async def get_bundle_context(self, **kwargs) -> Dict[str, Any]:
        # Implementation using existing DevHub functions
        pass
    
    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        # Main request handler
        pass
```

## Integration with Claude Desktop

### Configuration
```json
{
  "mcpServers": {
    "devhub": {
      "command": "uv",
      "args": ["run", "devhub-mcp"],
      "env": {
        "DEVHUB_CONFIG": "~/.devhub/config.json"
      }
    }
  }
}
```

### Usage Examples

```
Human: Get the bundle context for PROJ-123

Claude calls: get-bundle-context(jira_key="PROJ-123", include_diff=true, include_comments=true)

Returns: Complete bundle with Jira issue, PR details, code diff, and review comments
```

## Implementation Plan

1. **Create MCP Server Module** (`src/devhub/mcp_server.py`)
2. **Add MCP Dependencies** to pyproject.toml
3. **Create MCP Entry Point** for command-line execution
4. **Add Configuration Support** for MCP-specific settings
5. **Create Documentation** for setup and usage

## Next Steps

- [ ] Research exact MCP protocol specification
- [ ] Create basic MCP server implementation
- [ ] Test with Claude Desktop integration
- [ ] Add comprehensive tool set
- [ ] Create setup documentation