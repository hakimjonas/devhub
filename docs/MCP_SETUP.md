# DevHub MCP Server Setup Guide

> **Complete setup guide for DevHub's Model Context Protocol (MCP) integration**

This guide will help you set up the DevHub MCP server to work with AI agents like Claude Desktop, enabling seamless integration of Jira issues, GitHub PRs, and code review data.

## Overview

The DevHub MCP server provides 5 powerful tools that AI agents can use:

1. **get-bundle-context** - Get comprehensive bundle with Jira, PR, diff, and comments
2. **get-jira-issue** - Fetch specific Jira issue details
3. **get-pr-details** - Fetch GitHub PR information with optional diff
4. **get-pr-comments** - Fetch unresolved PR review comments
5. **get-current-branch-context** - Auto-detect context for current branch

## Prerequisites

1. **DevHub Installation**: Ensure DevHub is properly installed and configured
2. **Git Repository**: MCP server must be run from within a git repository
3. **GitHub CLI**: `gh` command must be installed and authenticated
4. **Optional**: Jira credentials configured for Jira-related tools

## Installation

### Install DevHub with MCP Support

```bash
# Clone and install DevHub
git clone https://github.com/hakimjonas/devhub.git
cd devhub
uv sync

# Install globally (optional)
uv tool install .
```

### Verify MCP Server

```bash
# Test MCP server installation
uv run python -c "from devhub.mcp_server import DevHubMCPServer; print('MCP Server ready!')"

# Test MCP command
uv run devhub-mcp --help
```

## Claude Desktop Integration

### Step 1: Locate Claude Desktop Configuration

The configuration file is typically located at:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/claude/claude_desktop_config.json`

### Step 2: Add DevHub MCP Server

Add the following to your Claude Desktop configuration:

```json
{
  "mcpServers": {
    "devhub": {
      "command": "uv",
      "args": ["run", "devhub-mcp"],
      "cwd": "/path/to/your/project",
      "env": {
        "DEVHUB_ORGANIZATION": "your-org-name"
      }
    }
  }
}
```

### Step 3: Configure DevHub

Ensure your DevHub configuration is properly set up:

```bash
# Create/edit configuration
mkdir -p ~/.devhub
cat > ~/.devhub/config.json << 'EOF'
{
  "config_version": "1.0",
  "default_organization": "my-company",
  "organizations": {
    "my-company": {
      "description": "My Company Development",
      "jira": {
        "base_url": "https://mycompany.atlassian.net",
        "default_project_prefix": "PROJ"
      },
      "github": {
        "default_org": "my-github-org",
        "use_ssh": true
      }
    }
  }
}
EOF

# Set Jira credentials (if needed)
export JIRA_EMAIL="your-email@company.com"
export JIRA_API_TOKEN="your-jira-token"
```

### Step 4: Restart Claude Desktop

Close and restart Claude Desktop. You should now see DevHub tools available.

## Usage Examples

### Example 1: Get Bundle Context

```
Human: Get the complete bundle context for PROJ-123

Claude will use: get-bundle-context(jira_key="PROJ-123", include_diff=true, include_comments=true)
```

### Example 2: Current Branch Analysis

```
Human: Analyze the current branch I'm working on

Claude will use: get-current-branch-context(include_diff=true, include_comments=true)
```

### Example 3: Specific PR Review

```
Human: Get details for PR #456 including the diff

Claude will use: get-pr-details(pr_number=456, include_diff=true)
```

### Example 4: Review Comments Analysis

```
Human: Show me the unresolved comments on PR #789

Claude will use: get-pr-comments(pr_number=789, limit=20)
```

## Advanced Configuration

### Multi-Project Setup

For multiple projects, you can configure different working directories:

```json
{
  "mcpServers": {
    "devhub-project-a": {
      "command": "uv",
      "args": ["run", "devhub-mcp"],
      "cwd": "/path/to/project-a",
      "env": {
        "DEVHUB_ORGANIZATION": "client-a"
      }
    },
    "devhub-project-b": {
      "command": "uv",
      "args": ["run", "devhub-mcp"],
      "cwd": "/path/to/project-b",
      "env": {
        "DEVHUB_ORGANIZATION": "client-b"
      }
    }
  }
}
```

### Environment Variables

Available environment variables:

- `DEVHUB_ORGANIZATION`: Override default organization
- `JIRA_EMAIL`: Jira authentication email
- `JIRA_API_TOKEN`: Jira API token
- `DEVHUB_CONFIG`: Path to DevHub configuration file
- `DEVHUB_DEBUG`: Enable debug logging

### Custom Configuration Path

```json
{
  "mcpServers": {
    "devhub": {
      "command": "uv",
      "args": ["run", "devhub-mcp"],
      "cwd": "/path/to/project",
      "env": {
        "DEVHUB_CONFIG": "/path/to/custom/config.json"
      }
    }
  }
}
```

## Other MCP Clients

### Generic MCP Client Setup

For other MCP clients, the DevHub server can be started directly:

```bash
# Start MCP server (reads from stdin, writes to stdout)
cd /path/to/your/project
uv run devhub-mcp
```

### Integration with Custom Tools

```python
import asyncio
import json
import subprocess
from typing import Any, Dict

async def call_devhub_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Call DevHub MCP tool programmatically."""
    request = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        },
        "id": 1
    }
    
    # Start MCP server process
    proc = subprocess.Popen(
        ["uv", "run", "devhub-mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd="/path/to/project"
    )
    
    # Send request
    stdout, stderr = proc.communicate(json.dumps(request) + "\n")
    
    if proc.returncode != 0:
        raise RuntimeError(f"MCP server error: {stderr}")
    
    return json.loads(stdout)

# Example usage
async def main():
    result = await call_devhub_tool("get-jira-issue", {"jira_key": "PROJ-123"})
    print(json.dumps(result, indent=2))

asyncio.run(main())
```

## Troubleshooting

### Common Issues

#### 1. MCP Server Not Starting

**Error**: "Command not found: devhub-mcp"

**Solution**:
```bash
# Ensure DevHub is properly installed
uv sync
pip install -e .

# Test direct import
python -c "from devhub.mcp_server import main; print('OK')"
```

#### 2. Authentication Issues

**Error**: "Jira credentials not configured"

**Solution**:
```bash
# Set environment variables
export JIRA_EMAIL="your@email.com"
export JIRA_API_TOKEN="your-token"

# Or configure in DevHub config
```

#### 3. Git Repository Issues

**Error**: "Failed to get repository info"

**Solution**:
```bash
# Ensure you're in a git repository
cd /path/to/git/repo
git status

# Ensure GitHub CLI is authenticated
gh auth login
```

#### 4. Permission Issues

**Error**: "Permission denied"

**Solution**:
```bash
# Check file permissions
chmod +x $(which devhub-mcp)

# Check configuration file permissions
chmod 600 ~/.devhub/config.json
```

### Debug Mode

Enable debug logging for troubleshooting:

```json
{
  "mcpServers": {
    "devhub": {
      "command": "uv",
      "args": ["run", "devhub-mcp"],
      "cwd": "/path/to/project",
      "env": {
        "DEVHUB_DEBUG": "1"
      }
    }
  }
}
```

### Testing MCP Tools

You can test individual MCP tools using a simple JSON request:

```bash
# Create test request
echo '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}' | uv run devhub-mcp

# Test tool call
echo '{"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "get-current-branch-context", "arguments": {}}, "id": 1}' | uv run devhub-mcp
```

## Security Considerations

1. **Credentials**: Never store API tokens in configuration files - use environment variables
2. **File Permissions**: Restrict access to configuration files (`chmod 600`)
3. **Network**: MCP server runs locally and doesn't expose network ports
4. **Logging**: Avoid logging sensitive information in debug mode

## Performance Tips

1. **Repository Location**: Run from project root for optimal performance
2. **Branch Context**: Use `get-current-branch-context` for auto-detection
3. **Comment Limits**: Adjust comment limits based on your needs
4. **Caching**: DevHub caches some data internally for better performance

## Next Steps

- **Explore Tools**: Try all 5 MCP tools with different parameters
- **Custom Workflows**: Create custom AI workflows using DevHub context
- **Integration**: Integrate with your existing development tools
- **Feedback**: Report issues and suggest improvements

---

The DevHub MCP server provides powerful AI integration capabilities while maintaining the functional programming excellence and type safety of the core DevHub system.