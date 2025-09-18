# DevHub Professional Installation Guide

## Installation Methods (Choose One)

### Method 1: Install with `uv tool` (Recommended - Fast!)
```bash
# Install DevHub globally as a tool
uv tool install --from /path/to/devhub devhub

# Now use from anywhere!
cd /any/project
devhub --help
```

### Method 2: Install with `pipx` (Standard Python Tools)
```bash
# Install pipx if you don't have it
python3 -m pip install --user pipx
python3 -m pipx ensurepath

# Install DevHub globally
pipx install /path/to/devhub

# Use from anywhere!
devhub --help
```

### Method 3: System-wide with pip
```bash
# Install globally (requires admin)
sudo pip install /path/to/devhub

# Or user-install
pip install --user /path/to/devhub
```

## First-Time Setup (One Time Only)

### 1. Initialize DevHub (stores config in ~/.devhub/)
```bash
# Run from anywhere - this sets up ~/.devhub/
devhub init

# This will:
# - Create ~/.devhub/config.yaml
# - Set up ~/.devhub/vault/ for credentials
# - Configure default settings
```

### 2. Configure Credentials (Secure)
```bash
# Store your API tokens securely
devhub auth setup

# Interactive prompts:
# > GitHub Token: ****
# > Jira URL: https://company.atlassian.net
# > Jira Token: ****
```

## Using DevHub in Your Projects

### For Any Project (No Setup Required!)
```bash
# Go to any project
cd /path/to/your/project

# Generate enhanced Claude context immediately
devhub claude context

# Bundle for code review
devhub bundle --pr 123

# Check what DevHub detects
devhub status
```

### Optional: Project-Specific Config
```bash
# Only if you want project-specific settings
cd /path/to/your/project
devhub init --project

# Creates .devhub.yaml in current directory (optional)
# This overrides global config for this project only
```

## How It Works (Like Git!)

```
~/.devhub/                    # Global DevHub home (like ~/.gitconfig)
├── config.yaml              # Global configuration
├── vault/                   # Encrypted credentials
│   ├── master.key          # Master key (encrypted)
│   └── credentials.db      # Encrypted credential store
└── cache/                  # Performance cache

/your/project/              # Your project - stays clean!
├── src/                    # Your code
├── tests/                  # Your tests
└── .devhub.yaml           # Optional project override
```

## Common Commands

```bash
# From ANY directory:
devhub --version            # Check version
devhub --help              # Get help

# From a project directory:
devhub status              # Show project detection
devhub claude context      # Generate Claude context
devhub bundle              # Create comprehensive bundle
devhub pr review 123       # Get PR review context

# Configuration:
devhub config set github.org "my-company"
devhub config get jira.url
devhub auth status         # Check credential status
```

## Professional Workflow

### 1. Install Once
```bash
uv tool install devhub
```

### 2. Configure Once
```bash
devhub init
devhub auth setup
```

### 3. Use Everywhere
```bash
# Project A
cd ~/projects/backend-api
devhub claude context > context.md

# Project B
cd ~/projects/frontend-app
devhub bundle --claude

# Project C (with GitLab)
cd ~/projects/gitlab-project
devhub status  # Auto-detects GitLab!
```

## No Project Contamination!

DevHub NEVER adds these to your project:
- ❌ No `node_modules/`
- ❌ No `.venv/`
- ❌ No `__pycache__/`
- ❌ No build artifacts

DevHub ONLY adds (if you explicitly request):
- ✅ `.devhub.yaml` - Optional project config (like `.gitignore`)

## Comparison with Other Tools

| Tool | Installation | Usage | Config Location |
|------|-------------|-------|-----------------|
| git | System/brew | `git ...` | `~/.gitconfig` + `.git/` |
| docker | System/brew | `docker ...` | `~/.docker/` |
| gh (GitHub CLI) | brew/system | `gh ...` | `~/.config/gh/` |
| **devhub** | uv tool/pipx | `devhub ...` | `~/.devhub/` |

## Uninstallation (Clean)

```bash
# Remove tool
uv tool uninstall devhub
# or
pipx uninstall devhub

# Remove config and credentials (optional)
rm -rf ~/.devhub/
```

## Why This Approach?

1. **Clean**: Your projects stay pristine
2. **Global**: Use DevHub in any project instantly
3. **Secure**: Credentials in encrypted user vault
4. **Fast**: No per-project installation needed
5. **Professional**: Works like git, docker, etc.

---

*DevHub - A proper development tool that respects your projects* ✨