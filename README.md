# DevHub

> **A functional programming exemplar for developers who demand excellence**

DevHub is a sophisticated CLI tool that demonstrates clean, maintainable Python code through **immutable data structures**, **pure functions**, and **comprehensive type safety**. It seamlessly integrates Jira issues, GitHub pull requests, code diffs, and review comments into organized bundles for efficient offline code review.

## 📚 Documentation

- **SDK Guide**: [docs/SDK_GUIDE.md](docs/SDK_GUIDE.md) - Complete guide to the DevHubClient async API
- **IDE Integrations**: [docs/IDE_INTEGRATIONS.md](docs/IDE_INTEGRATIONS.md) - Step-by-step VS Code and Cursor integration guides

## 🚀 Features

### Core Functionality
- **Comprehensive Bundle Generation**: Combines Jira issues, GitHub PRs, diffs, and review comments into structured bundles
- **Intelligent Auto-Detection**: Automatically resolves Jira keys and PR numbers from branch names and repository context
- **Flexible Output Formats**: Generate both human-readable files and structured JSON for programmatic use
- **Selective Data Inclusion**: Fine-grained control over what data to include (Jira, PR, diff, comments)

### Architecture & Quality
- **Organization-First Configuration**: Multi-tenant support with hierarchical configuration system
- **Immutable Data Architecture**: All data structures are frozen dataclasses ensuring thread safety
- **Type-Safe Operations**: 100% type coverage with strict mypy and pyright compliance
- **Functional Error Handling**: Uses `returns.Result` for explicit error propagation without exceptions
- **Property-Based Testing**: Comprehensive test suite with Hypothesis for robust validation (92.89% coverage)
- **Zero-Mutation Design**: Pure functions and immutable collections throughout

### AI Agent Integration
- **MCP (Model Context Protocol) Server**: Native support for AI agents like Claude Desktop
- **Async-First SDK**: High-performance `DevHubClient` for programmatic access
- **Real-Time Context**: Live development context for AI-assisted code review and analysis

## 📋 Requirements

- **Python 3.13+** (leverages latest type system improvements)
- **Git** (repository context and branch detection)
- **GitHub CLI (`gh`)** installed and authenticated
- **Optional**: Jira API credentials for issue integration

## 🛠️ Installation

DevHub provides multiple installation methods to suit different use cases and environments.

### 📦 PyPI (Recommended for End Users)

```bash
# Install from PyPI using pip
pip install devhub

# Or using pipx (recommended for CLI tools)
pipx install devhub

# Verify installation
devhub --version
devhub doctor
```

### ⚡ UV Tool (Modern Python Package Manager)

```bash
# Install globally using uv
uv tool install devhub

# Install from PyPI using uv
uv add devhub

# Verify installation
devhub --version
devhub doctor
```

### 🔧 Development Installation

```bash
# Clone the repository
git clone https://github.com/hakimjonas/devhub.git
cd devhub

# Install dependencies and development tools
uv sync
uv run pre-commit install

# Run in development mode
uv run devhub --version
uv run devhub doctor

# Run tests
uv run pytest
```

## 🎯 Quick Start

### Basic Usage

```bash
# Navigate to any git repository
cd /path/to/your/git/repo

# Run health check to verify setup
devhub doctor

# Auto-detect and bundle current branch context
devhub bundle

# Bundle specific Jira issue with auto-detected PR
devhub bundle --jira-key PROJ-123

# Bundle specific PR with auto-detected Jira issue
devhub bundle --pr-number 456

# Bundle with selective data inclusion
devhub bundle --jira-key PROJ-123 --no-diff --no-comments

# Generate JSON output for programmatic use
devhub bundle --jira-key PROJ-123 --format json
```

### Setup Wizard

For first-time setup, DevHub provides an interactive configuration wizard:

```bash
# Run the setup wizard (auto-detects if configuration is needed)
devhub doctor

# The wizard will guide you through:
# - GitHub CLI authentication verification
# - Jira credentials setup (optional)
# - Organization configuration
# - Testing your setup
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

- **`get-bundle-context`** - Comprehensive bundle with Jira issue, PR details, diff, and comments
- **`get-jira-issue`** - Fetch specific Jira issue details  
- **`get-pr-details`** - Fetch GitHub PR information with optional diff
- **`get-pr-comments`** - Fetch unresolved PR review comments
- **`get-current-branch-context`** - Auto-detect and get context for current git branch

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
