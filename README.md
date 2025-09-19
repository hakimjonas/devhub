# DevHub

> **Transform Claude Code into your development orchestrator**

DevHub is a professional CLI tool that enhances Claude Code interactions by providing rich project context from GitHub, GitLab, Jira, and your local repository. Built with **platform-agnostic architecture**, **enterprise-grade security**, and **user-centric design** for seamless multi-platform development workflows.

## 📚 Documentation

- **SDK Guide**: [docs/SDK_GUIDE.md](docs/SDK_GUIDE.md) - Complete guide to the DevHubClient async API
- **IDE Integrations**: [docs/IDE_INTEGRATIONS.md](docs/IDE_INTEGRATIONS.md) - Step-by-step VS Code and Cursor integration guides

## 🚀 Features

### 🌍 Multi-Platform Excellence
- **Platform Agnostic**: Equal first-class support for GitHub, GitLab, and local git
- **No Platform Favoritism**: Seamless workflows across different platforms
- **Migration Ready**: Zero-disruption transitions (GitHub → GitLab, mixed environments)
- **Flexible Configuration**: Per-project settings with intelligent defaults

### 🧙‍♂️ User-Centric Setup
- **Smart Setup Wizard**: Complete guided setup with auto-detection
- **Credential Security**: Encrypted vault with AES-256 encryption
- **SSH Detection**: Automatic authentication discovery
- **Team-Specific Patterns**: Supports team ticket prefixes (DATAEX-, BACKEND-, etc.)

### 🤖 Claude Code Integration
- **Enhanced Context**: Transform basic assistance into strategic partnership
- **Project Intelligence**: Comprehensive understanding of your codebase
- **Real-Time Insights**: Live development context for AI-assisted workflows
- **Strategic Guidance**: Move beyond generic advice to project-specific recommendations

### 🏗️ Professional Architecture
- **Global Tool Installation**: Install once, use everywhere (like git, docker)
- **Project-Based Configuration**: Clean, non-contaminating setup per project
- **Enterprise Security**: Secure credential management with audit logging
- **Type-Safe Operations**: Built with Python 3.13 and strict type checking

## 📋 Requirements

- **Python 3.13+** (leverages latest type system improvements)
- **Git** (repository context and branch detection)
- **GitHub CLI (`gh`)** installed and authenticated
- **Optional**: Jira API credentials for issue integration

## 🛠️ Installation

DevHub follows professional tool practices with global installation and per-project configuration.

### ⚡ Quick Install (Recommended)

```bash
# Method 1: UV tool (fastest, modern)
uv tool install --from /path/to/devhub devhub

# Method 2: Pipx (standard, reliable)
pipx install /path/to/devhub

# Method 3: Automated installer
python3 install_global.py
```

**Benefits:**
- ✅ **Global Tool**: Install once, use anywhere (like `git`, `docker`)
- ✅ **Clean Projects**: Never contaminates project directories
- ✅ **Professional CLI**: Follows Unix philosophy and best practices
- ✅ **Fast Setup**: 30-second installation with `uv`

### 🔧 Development Installation

```bash
# Clone and install for development
git clone https://github.com/hakimjonas/devhub.git
cd devhub

# Install in editable mode
uv tool install --editable .

# Install dependencies and development tools
uv sync
uv run pre-commit install

# Run tests
uv run pytest
```

## 🎯 Quick Start

### Simple 3-Step Setup

```bash
# 1. Navigate to your project
cd /path/to/your/project

# 2. Initialize DevHub (runs smart setup wizard)
devhub init

# 3. Start using enhanced Claude Code integration
devhub claude context
```

### 🧙‍♂️ Smart Setup Wizard

The wizard auto-detects your environment and guides you through setup:

```bash
devhub init  # Complete setup wizard (default)
```

**The wizard detects:**
- ✅ **Repository Platform**: GitHub, GitLab, or local git
- ✅ **Authentication**: SSH keys, GitHub CLI, environment tokens
- ✅ **Jira Integration**: Auto-detects Jira URLs and project keys
- ✅ **Team Patterns**: Finds your ticket prefixes (DATAEX-, BACKEND-)

### Real-World Examples

```bash
# Work Project (GitHub + Jira + DATAEX tickets)
cd /work/backend-service
devhub init
# Wizard detects: GitHub, Jira URL, DATAEX- pattern

# Personal Project (GitHub + GitHub Projects)
cd /personal/side-project
devhub init
# Wizard detects: GitHub, suggests GitHub Projects

# Work Project (GitLab + Jira + team-specific tickets)
cd /work/new-microservice
devhub init
# Wizard detects: GitLab, Jira URL, multiple team patterns
```

### Configuration

DevHub supports both environment variables and configuration files:

```bash
# Environment variables (recommended for CI/CD)
export JIRA_BASE_URL="https://your-domain.atlassian.net"
export JIRA_EMAIL="your.email@company.com"
export JIRA_API_TOKEN="your-api-token"
export GITHUB_TOKEN="your-github-token"

# Or use configuration file (~/.config/devhub/config.toml)
# See devhub doctor for configuration guidance
```

### Output Structure

DevHub creates organized bundle directories:

```
PROJ-123-20241203-143022/
├── bundle.json              # Structured data for programmatic use
├── 1-jira-issue.md         # Jira issue details
├── 2-pr-details.md         # GitHub PR information
├── 3-pr-diff.patch         # Code changes
└── 4-unresolved-comments.md # Review comments needing attention
```

## 🤖 AI Agent Integration (MCP Mode)

DevHub can be used as an MCP (Model Context Protocol) server for AI agents like Claude Desktop, providing real-time access to development context.

### MCP Server Commands

```bash
# Show available MCP tools and setup instructions
devhub claude mcp

# Show help and available options
devhub-mcp --help

# List available MCP tools
devhub-mcp --tools

# Test MCP server functionality
devhub-mcp --test

# Run as MCP server (default mode)
devhub-mcp
```

### Claude Desktop Configuration

Add DevHub to your Claude Desktop configuration (`~/.config/claude-desktop/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "devhub": {
      "command": "devhub-mcp",
      "args": [],
      "env": {
        "JIRA_BASE_URL": "https://your-domain.atlassian.net",
        "JIRA_EMAIL": "your.email@company.com",
        "JIRA_API_TOKEN": "your-api-token",
        "GITHUB_TOKEN": "your-github-token"
      }
    }
  }
}
```

### MCP Tools Available

When connected as an MCP server, DevHub provides these tools to AI agents:

**📖 READ OPERATIONS:**
- **`get-bundle-context`** - Comprehensive bundle with Jira issue, PR details, diff, and comments
- **`get-jira-issue`** - Fetch specific Jira issue details
- **`get-pr-details`** - Fetch GitHub PR information with optional diff
- **`get-pr-comments`** - Fetch unresolved PR review comments
- **`get-current-branch-context`** - Auto-detect and get context for current git branch

**✏️ WRITE OPERATIONS:**
- **`update-jira-issue`** - Update Jira issue fields (summary, description)

### MCP Usage Examples

Once configured, AI agents can use natural language to:

```
"Get the context for PROJ-123 including the diff and unresolved comments"
"Show me the details of PR #456 without the full diff"
"What's the current status of my branch and any related PRs?"
"Fetch all unresolved review comments for the current PR"
```

## 🧩 Programmatic Usage

For advanced integration and custom tooling, use the async SDK:

```python
import asyncio
from devhub.sdk import DevHubClient, ContextRequest
from returns.result import Success, Failure

async def main():
    # Create a context request
    request = ContextRequest(
        jira_key="PROJ-123",
        include_diff=True,
        include_comments=True,
        comment_limit=20
    )
    
    # Use the async client
    client = DevHubClient()
    await client.initialize()
    
    result = await client.get_bundle_context(request)
    
    match result:
        case Success(bundle):
            print(f"Repository: {bundle.repository.owner}/{bundle.repository.name}")
            print(f"Branch: {bundle.branch}")
            if bundle.jira_issue:
                print(f"Jira: {bundle.jira_issue.key} - {bundle.jira_issue.summary}")
            print(f"Unresolved comments: {len(bundle.comments)}")
        case Failure(error):
            print(f"Error: {error}")

asyncio.run(main())
```

See [docs/SDK_GUIDE.md](docs/SDK_GUIDE.md) for complete SDK documentation and examples.

## 📊 Command Reference

### Bundle Command

```bash
devhub bundle [OPTIONS]

Options:
  --jira-key TEXT        Jira issue key (e.g., PROJ-123)
  --pr-number INTEGER    Pull request number
  --branch TEXT          Git branch name (defaults to current)
  --output-dir TEXT      Output directory (defaults to auto-generated)
  --organization TEXT    GitHub organization override
  --limit INTEGER        Limit for comments (default: 10)
  --format FORMAT        Output format: files|json (default: files)
  --no-jira             Exclude Jira data
  --no-pr               Exclude PR data  
  --no-diff             Exclude PR diff
  --no-comments         Exclude unresolved comments
```

### Doctor Command

```bash
devhub doctor

# Comprehensive health check including:
# - Python version verification
# - Git repository detection
# - GitHub CLI authentication
# - Jira credentials validation
# - Configuration file verification
# - Network connectivity tests
```

## 🔧 Development

### Code Quality Standards

DevHub maintains exceptional code quality through:

- **100% Type Coverage**: Strict mypy and pyright compliance
- **92.89% Test Coverage**: Comprehensive pytest suite with property-based testing
- **Zero Warnings**: Clean ruff, bandit, and semgrep scans
- **Functional Purity**: Immutable data structures and pure functions
- **Comprehensive Documentation**: All public APIs documented

### Running Tests

```bash
# Full test suite with coverage
uv run pytest

# Run specific test categories
uv run pytest -m unit
uv run pytest -m integration
uv run pytest -m property

# Performance testing
uv run pytest -m slow

# Parallel execution
uv run pytest -n auto
```

### Code Quality Checks

```bash
# Type checking
uv run mypy src/devhub
uv run pyright src/devhub

# Linting and formatting
uv run ruff check src/devhub
uv run ruff format src/devhub

# Security scanning
uv run bandit -r src/devhub
uv run semgrep --config=auto src/devhub

# Dead code detection
uv run vulture src/devhub
```

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 🤝 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Key Principles

- **Functional Programming**: Prefer immutable data and pure functions
- **Type Safety**: All code must pass strict type checking
- **Test Coverage**: Maintain >90% coverage with meaningful tests
- **Documentation**: Document all public APIs and design decisions

## 🔗 Links

- **Repository**: https://github.com/hakimjonas/devhub
- **Issues**: https://github.com/hakimjonas/devhub/issues
- **PyPI**: https://pypi.org/project/devhub/
- **Documentation**: [docs/](docs/)

---

DevHub exemplifies modern Python development practices while solving real-world code review challenges. Built with functional programming principles for reliability, maintainability, and extensibility.
