# DevHub

> **A functional programming exemplar for developers who demand excellence**

DevHub is a sophisticated CLI tool that demonstrates clean, maintainable Python code through **immutable data structures**, **pure functions**, and **comprehensive type safety**. It seamlessly integrates Jira issues, GitHub pull requests, code diffs, and review comments into organized bundles for efficient offline code review.

## 📚 Documentation

- SDK Guide (async-first usage with DevHubAsyncClient): docs/SDK_GUIDE.md
- IDE Integrations (VS Code and Cursor step-by-step): docs/IDE_INTEGRATIONS.md

## 🚀 Features

- **Organization-First Configuration**: Multi-tenant support with hierarchical configuration system
- **Immutable Data Architecture**: All data structures are frozen dataclasses ensuring thread safety
- **Type-Safe Operations**: 100% type coverage with strict mypy and pyright compliance
- **Functional Error Handling**: Uses `returns.Result` for explicit error propagation
- **Property-Based Testing**: Comprehensive test suite with Hypothesis for robust validation
- **Zero-Mutation Design**: Pure functions and immutable collections throughout

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

# Or install from Git repository
uv tool install git+https://github.com/hakimjonas/devhub.git

# Verify installation
devhub --version
devhub doctor
```

### 🐳 Docker (Containerized)

```bash
# Pull and run from GitHub Container Registry
docker run --rm ghcr.io/hakimjonas/devhub:latest --version

# Interactive usage with mounted workspace
docker run --rm -it \
  -v $(pwd):/workspace \
  -v ~/.config/devhub:/home/devhub/.config/devhub:ro \
  -v ~/.config/gh:/home/devhub/.config/gh:ro \
  ghcr.io/hakimjonas/devhub:latest doctor

# Using docker-compose for development
docker-compose run --rm devhub doctor
```

### 🍺 Homebrew (macOS/Linux)

```bash
# Install from local formula (development)
git clone https://github.com/hakimjonas/devhub.git
cd devhub
brew install --build-from-source homebrew/devhub.rb

# Future: Install from tap (when published)
# brew tap hakimjonas/devhub
# brew install devhub

# Verify installation
devhub --version
devhub doctor
```

### 🔧 Development Setup

```bash
# Clone and set up development environment
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

### 🔍 Installation Verification

After installation, verify DevHub is working correctly:

```bash
# Check version
devhub --version
# Output: devhub 0.1.0

# Run comprehensive health checks
devhub doctor
# Output: DevHub Health Check Results with system status

# View available commands
devhub --help

# Test basic functionality (in a git repository)
devhub bundle --help
```

### 🎯 Quick Start Test

```bash
# Navigate to any git repository
cd /path/to/your/git/repo

# Run health check to verify setup
devhub doctor

# Create a test bundle (requires GitHub CLI authentication)
devhub bundle --jira-key TEST-123
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
"Show me the context for JIRA-123 including the PR and comments"
→ Uses get-bundle-context with jira_key="JIRA-123"

"Get the details for PR #42 without the diff"  
→ Uses get-pr-details with pr_number=42, include_diff=false

"What's the current branch context?"
→ Uses get-current-branch-context to auto-detect and fetch context
```

### 🐛 Troubleshooting Installation

If you encounter issues:

1. **Check dependencies**:
   ```bash
   devhub doctor  # Shows missing dependencies
   ```

2. **Verify GitHub CLI is installed and authenticated**:
   ```bash
   gh auth status
   ```

3. **For Docker issues**, ensure Docker is running:
   ```bash
   docker --version
   docker run hello-world
   ```

4. **For permission issues** with pip:
   ```bash
   pip install --user devhub  # Install for current user only
   ```

5. **For Python version conflicts**:
   ```bash
   python --version  # Should be 3.13+
   pipx install devhub  # Isolated installation
   ```

## ⚙️ Configuration

DevHub uses a hierarchical configuration system supporting multiple organizations with different settings.

### Configuration File Locations

DevHub follows the XDG Base Directory specification and searches for configuration files in this order:

1. **`DEVHUB_CONFIG`** - Explicit config file path (environment variable)
2. **`.devhub.json`** - Project-local configuration
3. **`$XDG_CONFIG_HOME/devhub/config.json`** - User XDG config (default: `~/.config/devhub/config.json`)
4. **`$XDG_CONFIG_DIRS/devhub/config.json`** - System XDG config dirs (default: `/etc/xdg/devhub/config.json`)

#### Configuration Override Examples

**Explicit configuration file:**
```bash
export DEVHUB_CONFIG="/path/to/my/devhub-config.json"
devhub bundle  # Uses the specified config file
```

**Custom XDG paths:**
```bash
export XDG_CONFIG_HOME="/custom/config"
# DevHub will look for /custom/config/devhub/config.json

export XDG_CONFIG_DIRS="/etc/xdg:/usr/local/etc:/opt/etc"
# DevHub will search each directory for devhub/config.json
```

**Recommended locations for new users:**
- **User configuration:** `~/.config/devhub/config.json`
- **System configuration:** `/etc/xdg/devhub/config.json`
- **Container/CI environments:** Use `DEVHUB_CONFIG` to specify exact path

### Basic Configuration

Create `~/.config/devhub/config.json` (recommended XDG location):

```json
{
  "config_version": "1.0",
  "default_organization": "my-company",
  "organizations": {
    "my-company": {
      "description": "My Company Development",
      "jira": {
        "base_url": "https://mycompany.atlassian.net",
        "default_project_prefix": "PROJ",
        "timeout_seconds": 30
      },
      "github": {
        "default_org": "my-company",
        "use_ssh": true
      },
      "output": {
        "base_directory": "review-bundles",
        "include_timestamps": true
      },
      "bundle_defaults": {
        "include_jira": true,
        "include_pr": true,
        "include_diff": true,
        "include_comments": true,
        "comment_limit": 15,
        "diff_context_lines": 3
      }
    }
  },
  "global_jira": {
    "timeout_seconds": 45,
    "max_retries": 3
  }
}
```

### Multi-Organization Setup

For teams working with multiple organizations:

```json
{
  "config_version": "1.0",
  "default_organization": "client-a",
  "organizations": {
    "client-a": {
      "description": "Client A Projects",
      "jira": {
        "base_url": "https://clienta.atlassian.net",
        "default_project_prefix": "CA"
      },
      "github": {
        "default_org": "client-a-org"
      }
    },
    "client-b": {
      "description": "Client B Projects", 
      "jira": {
        "base_url": "https://clientb.atlassian.net",
        "default_project_prefix": "CB"
      },
      "github": {
        "default_org": "client-b-org"
      }
    },
    "internal": {
      "description": "Internal Tools",
      "github": {
        "default_org": "my-company"
      }
    }
  }
}
```

### Environment Variables

#### Configuration File Override

```bash
# Explicit config file path (highest priority)
export DEVHUB_CONFIG="/path/to/specific/config.json"

# XDG Base Directory specification
export XDG_CONFIG_HOME="/custom/config"      # Default: ~/.config
export XDG_CONFIG_DIRS="/etc/xdg:/usr/local/etc"  # Default: /etc/xdg
```

#### Credentials (Sensitive Data)

Sensitive credentials should use environment variables:

```bash
export JIRA_EMAIL="your-email@company.com"
export JIRA_API_TOKEN="your-jira-api-token"

# Optional: Override organization selection
export DEVHUB_ORGANIZATION="client-a"
```


## 🎯 Quick Start

### Basic Bundle Creation

```bash
# Bundle everything for current branch (auto-detects Jira key)
devhub bundle

# Bundle with specific Jira key  
devhub bundle --jira-key PROJ-123

# Bundle for specific PR
devhub bundle --pr 456

# Custom output location
devhub bundle --out ~/reviews/proj-123-review
```

### Selective Bundling

```bash
# Only Jira issue + PR metadata (skip diff and comments)
devhub bundle --no-diff --no-comments

# Only review comments with higher limit
devhub bundle --no-jira --no-pr --no-diff --limit 25

# PR and diff only (skip Jira and comments)
devhub bundle --no-jira --no-comments
```

## 📚 Command Reference

### `bundle` - Complete Review Package

Creates a comprehensive review bundle with all relevant information.

```bash
devhub bundle [OPTIONS]

Options:
  --jira-key KEY         Specific Jira issue key (e.g., PROJ-123)
  --pr NUMBER           Specific GitHub PR number
  --branch NAME         Branch name (for PR lookup and Jira key inference)
  --out DIRECTORY       Output directory path
  --limit NUMBER        Max unresolved comments to include (default: 10)
  --no-jira            Skip Jira issue fetching
  --no-pr              Skip PR metadata fetching  
  --no-diff            Skip PR diff fetching
  --no-comments        Skip review comments fetching
  --org ORGANIZATION   Override default organization
```

### Advanced Bundle Examples

```bash
# Bundle with organization override
devhub bundle --jira-key CA-456 --org client-a

# High-comment limit for complex reviews
devhub bundle --limit 50 --pr 789

# Minimal bundle for quick PR check
devhub bundle --no-jira --no-comments --pr 123
```

## 📁 Output Structure

DevHub creates organized directories with consistent naming:

```
review-bundles/
└── PROJ-123-20240128-143022/
    ├── jira_PROJ-123.json          # Complete Jira issue data
    ├── jira_PROJ-123.md            # Human-readable summary
    ├── pr_456.json                 # PR metadata and details
    ├── pr_456.md                   # Formatted PR information
    ├── pr_456.diff                 # Complete code diff
    └── unresolved_comments_pr456.json  # Review comments
```

### File Contents

- **Jira JSON**: Complete API response with all fields and metadata
- **Jira Markdown**: Clean summary with description, acceptance criteria, and links
- **PR JSON**: GitHub API response with full PR details
- **PR Markdown**: Formatted PR title, description, author, and key metadata  
- **Diff File**: Git-style unified diff of all changes
- **Comments JSON**: Structured unresolved review comments with context

## 🔧 Advanced Configuration

### Custom Output Formatting

```json
{
  "output": {
    "base_directory": "code-reviews",
    "include_timestamps": false,
    "file_permissions": 644,
    "directory_permissions": 755
  }
}
```

### Jira Integration Tuning

```json
{
  "jira": {
    "base_url": "https://company.atlassian.net",
    "timeout_seconds": 60,
    "max_retries": 5,
    "default_project_prefix": "MYPROJ"
  }
}
```

### GitHub API Optimization

```json
{
  "github": {
    "timeout_seconds": 45,
    "max_retries": 3,
    "use_ssh": true,
    "default_org": "my-github-org"
  }
}
```

## 🧪 Development & Testing

DevHub maintains exceptional code quality standards:

```bash
# Run complete test suite with coverage
uv run pytest --cov-report=html

# Type checking with multiple tools
uv run mypy src/
uv run pyright src/

# Linting and formatting
uv run ruff check .
uv run ruff format .

# Security scanning
uv run bandit -r src/
uv run semgrep --config=auto src/

# Property-based testing
uv run pytest tests/ -k property
```

### Quality Metrics

- **Test Coverage**: 87%+ with meaningful path coverage
- **Type Safety**: 100% type annotation coverage
- **Code Quality**: Ruff with ALL rules enabled
- **Security**: Regular scanning with bandit and semgrep
- **Functional Purity**: Immutable data structures throughout

## 🔍 Troubleshooting

### Common Issues

#### Authentication Problems
```bash
# GitHub CLI not authenticated
gh auth login

# Jira credentials issues
export JIRA_EMAIL="your-email@domain.com"
export JIRA_API_TOKEN="your-api-token"
```

#### Repository Context
```bash
# Must be run inside a Git repository
cd /path/to/your/git/repo
devhub bundle
```

#### PR Detection Issues
```bash
# Specify PR explicitly if auto-detection fails
devhub bundle --pr 123

# Or specify exact branch name
devhub bundle --branch "feature/PROJ-123-add-feature"
```

### Debug Mode

Enable verbose logging for troubleshooting:

```bash
export DEVHUB_DEBUG=1
devhub bundle --jira-key PROJ-123
```

## 🏛️ Architecture Philosophy

DevHub exemplifies functional programming principles in Python:

### Immutability First
- All data structures are `@dataclass(frozen=True)`
- No mutable state or in-place modifications
- Thread-safe by design

### Type Safety Excellence
- Comprehensive type hints with `mypy` strict mode
- `returns.Result` for explicit error handling
- No `Any` types except for external API boundaries

### Pure Functions
- Side effects isolated to dedicated modules
- Predictable input/output relationships
- Easy testing and reasoning

### Composition Over Inheritance
- Data transformation pipelines
- Function composition patterns
- Modular, reusable components

## 🤝 Contributing

We welcome contributions that maintain our high standards:

1. **Follow Functional Programming Guidelines**: See [CONTRIBUTING.md](CONTRIBUTING.md)
2. **Maintain Type Safety**: All code must pass `mypy --strict`
3. **Add Comprehensive Tests**: Include unit, integration, and property-based tests
4. **Document Thoroughly**: Use Google-style docstrings
5. **Use Immutable Patterns**: No mutable data structures

### Development Workflow

```bash
# Set up development environment
uv sync
uv run pre-commit install

# Run quality checks
uv run pytest
uv run mypy src/
uv run ruff check .

# Submit changes
git commit -m "feat(core): add immutable feature"
```

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

**DevHub**: *Where functional programming meets practical development tools.*
