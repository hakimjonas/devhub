# DevHub

> **A functional programming exemplar for developers who demand excellence**

DevHub is a sophisticated CLI tool that demonstrates clean, maintainable Python code through **immutable data structures**, **pure functions**, and **comprehensive type safety**. It seamlessly integrates Jira issues, GitHub pull requests, code diffs, and review comments into organized bundles for efficient offline code review.

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

### Using UV (Recommended)

```bash
# Clone the repository
git clone https://github.com/hakimjonas/devhub.git
cd devhub

# Install with UV (handles Python version automatically)
uv sync

# Make available globally
uv tool install .
```

### Using pip

```bash
# Install from PyPI (when published)
pip install devhub

# Or install from source
pip install git+https://github.com/hakimjonas/devhub.git
```

### Development Setup

```bash
# Clone and set up development environment
git clone https://github.com/hakimjonas/devhub.git
cd devhub
uv sync
uv run pre-commit install
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

