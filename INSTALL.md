# DevHub Professional Installation Guide

## Prerequisites

- Python 3.10 or higher
- Git (for version control integration)
- Active GitHub and/or Jira accounts with API access

## Installation Options

### Option 1: Local Development Installation (Recommended for Now)

Since DevHub is in active development, install it directly from your local directory:

```bash
# Navigate to the DevHub directory
cd /path/to/devhub

# Install in development mode (recommended)
pip install -e .

# Or install normally
pip install .
```

### Option 2: Install with All Dependencies

```bash
# Install with development tools
pip install -e ".[dev]"

# Install with testing tools
pip install -e ".[test]"
```

### Option 3: Package and Install

```bash
# Create a distributable package
cd /path/to/devhub
python setup.py sdist bdist_wheel

# Install from the package
pip install dist/devhub-0.1.0-py3-none-any.whl
```

## Verify Installation

```bash
# Check CLI is available
devhub --version

# Check Python import works
python -c "from devhub.sdk import DevHubClient; print('✅ DevHub imported successfully')"
```

## Quick Setup for Existing Projects

### 1. Install DevHub in Your Project

```bash
# Go to your existing project
cd /path/to/your/project

# Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install DevHub from local directory
pip install /path/to/devhub
```

### 2. Initialize DevHub Configuration

```bash
# Create basic configuration
cat > .devhub.yaml << 'EOF'
# DevHub Configuration
version: 1.0

github:
  enabled: true
  organization: "your-org"  # Update this

jira:
  enabled: true
  base_url: "https://your-company.atlassian.net"  # Update this

bundle:
  max_files: 100
  include_tests: true
  include_docs: true
  claude_optimized: true

platforms:
  primary: "github"  # or "gitlab" or "local"
EOF
```

### 3. Set Up Credentials

```python
#!/usr/bin/env python3
"""setup_credentials.py - Secure credential setup"""

import asyncio
import getpass
from pathlib import Path
from devhub.vault import SecureVault, CredentialMetadata, CredentialType, VaultConfig

async def setup_credentials():
    """Interactive credential setup."""

    print("🔐 DevHub Secure Credential Setup")
    print("=" * 40)

    # Initialize vault
    vault_dir = Path.home() / ".devhub" / "vault"
    vault_config = VaultConfig(vault_dir=vault_dir)
    vault = SecureVault(vault_config)

    # Get master password
    master_password = getpass.getpass("Create a master password for credential vault: ")
    confirm_password = getpass.getpass("Confirm master password: ")

    if master_password != confirm_password:
        print("❌ Passwords don't match. Please try again.")
        return

    try:
        await vault.initialize(master_password)
        print("✅ Vault initialized successfully")
    except Exception as e:
        print(f"❌ Error initializing vault: {e}")
        return

    # GitHub Token Setup
    print("\n📍 GitHub Token Setup")
    print("Go to: https://github.com/settings/tokens")
    print("Required scopes: repo, read:org, read:project")
    github_token = getpass.getpass("GitHub personal access token (or press Enter to skip): ")

    if github_token:
        await vault.store_credential(
            CredentialMetadata(
                name="github_token",
                credential_type=CredentialType.API_TOKEN,
                description="GitHub personal access token"
            ),
            github_token
        )
        print("✅ GitHub token stored securely")

    # Jira Setup
    print("\n📍 Jira Credentials Setup")
    print("Go to: https://id.atlassian.com/manage-profile/security/api-tokens")
    jira_email = input("Jira email (or press Enter to skip): ")

    if jira_email:
        jira_token = getpass.getpass("Jira API token: ")

        await vault.store_credential(
            CredentialMetadata(
                name="jira_email",
                credential_type=CredentialType.USERNAME,
                description="Jira account email"
            ),
            jira_email
        )

        await vault.store_credential(
            CredentialMetadata(
                name="jira_token",
                credential_type=CredentialType.API_TOKEN,
                description="Jira API token"
            ),
            jira_token
        )
        print("✅ Jira credentials stored securely")

    print("\n🎉 Credential setup complete!")
    print("Your credentials are encrypted and stored in:", vault_dir)

if __name__ == "__main__":
    asyncio.run(setup_credentials())
```

Save this as `setup_credentials.py` and run it:

```bash
python setup_credentials.py
```

### 4. Generate Enhanced Claude Context

```python
#!/usr/bin/env python3
"""generate_context.py - Generate enhanced context for Claude"""

import asyncio
from pathlib import Path
from devhub.claude_integration import claude_code_review_context

async def generate_context():
    """Generate enhanced context for Claude Code."""

    print("🧠 Generating Enhanced Claude Context")
    print("=" * 40)

    try:
        # Generate context
        context = await claude_code_review_context()

        if context and not isinstance(context, Exception):
            # Save to file
            output_file = Path("claude_context.md")
            with open(output_file, "w") as f:
                f.write(context)

            print(f"✅ Context saved to: {output_file}")
            print("\n📋 Preview:")
            print("-" * 40)
            print(context[:500] + "...")
            print("-" * 40)
            print("\n🚀 Copy this to Claude for enhanced interactions!")
        else:
            print("❌ Could not generate context. Check your configuration.")

    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nTroubleshooting:")
        print("1. Check .devhub.yaml configuration")
        print("2. Verify credentials are set up")
        print("3. Ensure you're in a Git repository")

if __name__ == "__main__":
    asyncio.run(generate_context())
```

## Troubleshooting

### Import Error: "No module named 'devhub'"

```bash
# Ensure DevHub is installed
pip list | grep devhub

# If not listed, reinstall
cd /path/to/devhub
pip install -e .
```

### Credential Issues

```bash
# Reset credentials
rm -rf ~/.devhub/vault
python setup_credentials.py
```

### Configuration Problems

```bash
# Validate configuration
python -c "
import yaml
with open('.devhub.yaml', 'r') as f:
    config = yaml.safe_load(f)
    print('✅ Configuration is valid')
    print(f'Platforms enabled: {list(config.keys())}')
"
```

## Next Steps

1. **Set up credentials**: Run `python setup_credentials.py`
2. **Configure platforms**: Edit `.devhub.yaml` with your GitHub org and Jira URL
3. **Generate context**: Run `python generate_context.py`
4. **Use with Claude**: Copy the generated context to Claude Code

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review example scripts in `/path/to/devhub/examples/`
3. Ensure all dependencies are installed: `pip install -r requirements.txt`

## Development Setup

For contributing to DevHub:

```bash
# Clone locally (since no GitHub repo yet)
cp -r /path/to/devhub ~/devhub-dev

# Install in development mode with all extras
cd ~/devhub-dev
pip install -e ".[dev,test]"

# Run tests
pytest

# Run type checking
mypy src/devhub

# Run linting
ruff check src/
```

---

*DevHub v0.1.0 - Transforming Claude Code into Your Development Orchestrator*