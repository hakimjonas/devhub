# 🚀 DevHub: Professional Installation & Usage

DevHub is a global command-line tool that enhances your Claude Code experience without contaminating your projects.

## Quick Installation (30 seconds)

### Fastest: Using `uv` (Recommended)
```bash
# Install uv if you don't have it (instant)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install DevHub globally
uv tool install --from /path/to/devhub devhub

# Ready to use!
devhub --version
```

### Alternative: Using `pipx` (Standard Python)
```bash
# Install pipx if you don't have it
python3 -m pip install --user pipx
python3 -m pipx ensurepath

# Install DevHub globally
pipx install /path/to/devhub

# Ready to use!
devhub --version
```

### Alternative: Automated Installer
```bash
# Run our smart installer (detects best method)
cd /path/to/devhub
python3 install_global.py

# Or on Unix/Linux/macOS:
bash install_global.sh
```

## First-Time Setup (One-time, 2 minutes)

### 1. Initialize DevHub
```bash
# Creates ~/.devhub/ configuration directory
devhub init

# Output:
# ✅ Created global config: ~/.devhub/config.yaml
```

### 2. Set Up Authentication
```bash
# Secure credential storage
devhub auth setup

# Interactive prompts:
# > Create vault password: ****
# > Configure GitHub? (y/n): y
# > GitHub token: ****
# > Configure Jira? (y/n): y
# > Jira URL: https://company.atlassian.net
# > Jira token: ****
```

## Usage (From Any Project!)

### Check Project Detection
```bash
cd /any/project
devhub status

# Output:
# ✅ Git repository detected
#   → GitHub repository
# 📦 Project type: Python (pyproject.toml)
```

### Generate Enhanced Claude Context
```bash
# In any project directory
cd /your/project
devhub claude context

# Output:
# ✅ Context saved to: claude_context.md
# 📋 Copy to Claude for enhanced interactions!
```

### Bundle for Code Review
```bash
devhub bundle --pr 123 --claude

# Bundles PR #123 with full context optimized for Claude
```

## How It Works

```
Your System:
├── ~/.devhub/                 # DevHub home (like ~/.docker/)
│   ├── config.yaml           # Global configuration
│   ├── vault/                # Encrypted credentials
│   └── cache/                # Performance cache
│
├── ~/.local/bin/devhub       # DevHub command (or in uv tools)
│
└── /your/projects/           # Your projects stay clean!
    ├── project-a/            # No DevHub files added
    ├── project-b/            # No contamination
    └── project-c/            # Optional .devhub.yaml only
```

## Key Benefits

### ✅ **Clean Projects**
- No `venv/` in your projects
- No `node_modules/` equivalent
- No build artifacts
- Projects stay pristine

### ✅ **Global Tool**
- Install once, use everywhere
- Like `git`, `docker`, `npm`
- Professional CLI patterns

### ✅ **Secure**
- Credentials in encrypted vault
- Stored in user home
- Never in project directories

### ✅ **Fast**
- No per-project setup
- Instant context generation
- Cached for performance

## Common Commands

```bash
# Help
devhub --help              # General help
devhub claude --help       # Claude commands help

# Configuration
devhub config show         # Show all config
devhub config set github.org "my-company"
devhub config get jira.url

# Authentication
devhub auth status         # Check auth status
devhub auth setup          # Set up credentials

# Claude Integration
devhub claude context      # Generate context
devhub claude review       # Review mode context

# Project Commands
devhub status             # Show project info
devhub bundle             # Create context bundle
```

## Project-Specific Config (Optional)

If you want project-specific settings:

```bash
cd /your/project
devhub init --project

# Creates .devhub.yaml in current directory
# This overrides global config for this project only
```

Example `.devhub.yaml`:
```yaml
version: 1.0
github:
  organization: "specific-org"
jira:
  project_key: "PROJ"
bundle:
  max_files: 200
  include_tests: true
```

## Troubleshooting

### Command not found
```bash
# Check installation
which devhub

# For uv installation
uv tool list

# For pipx installation
pipx list

# Add to PATH if needed
export PATH="$HOME/.local/bin:$PATH"
```

### Permission denied
```bash
# Check credentials
devhub auth status

# Re-initialize if needed
devhub auth setup
```

### Wrong project detection
```bash
# Check what DevHub sees
devhub status

# Force platform if needed
devhub config set platforms.primary "gitlab"
```

## Uninstall (Clean)

```bash
# Remove the tool
uv tool uninstall devhub
# or
pipx uninstall devhub

# Remove configuration (optional)
rm -rf ~/.devhub/
```

## Comparison with Development Tools

| Tool | Installation | Usage Pattern | Config Location |
|------|-------------|---------------|-----------------|
| **git** | `brew install git` | `git ...` | `~/.gitconfig` |
| **docker** | Download installer | `docker ...` | `~/.docker/` |
| **gh** | `brew install gh` | `gh ...` | `~/.config/gh/` |
| **ruff** | `pipx install ruff` | `ruff ...` | `~/.config/ruff/` |
| **devhub** | `uv tool install devhub` | `devhub ...` | `~/.devhub/` |

## Philosophy

DevHub follows Unix philosophy and modern CLI best practices:

1. **Do one thing well**: Enhance Claude Code context
2. **Global tool**: Install once, use anywhere
3. **No side effects**: Never modifies your projects
4. **Secure by default**: Encrypted credential storage
5. **Fast and efficient**: Cached and optimized

---

**Ready to transform your Claude Code experience without cluttering your projects!** ✨