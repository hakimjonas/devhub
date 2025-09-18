#!/usr/bin/env python3
"""One-command setup script for existing projects.

Usage:
    python immediate_setup_script.py

This script will:
1. Detect your project environment
2. Install DevHub if needed
3. Create configuration
4. Set up credentials securely
5. Generate your first enhanced Claude context
"""

import subprocess
from pathlib import Path


def check_git_repository() -> bool:
    """Check if we're in a Git repository."""
    return (Path.cwd() / ".git").exists()


def detect_project_type() -> dict[str, bool]:
    """Detect project characteristics."""
    cwd = Path.cwd()

    return {
        "is_git": check_git_repository(),
        "has_python": (cwd / "requirements.txt").exists() or (cwd / "pyproject.toml").exists(),
        "has_node": (cwd / "package.json").exists(),
        "has_java": (cwd / "pom.xml").exists() or (cwd / "build.gradle").exists(),
        "has_dotnet": any(cwd.glob("*.csproj")) or any(cwd.glob("*.sln")),
    }


def run_command(cmd: str, _description: str) -> bool:
    """Run a shell command and return success status."""
    try:
        result = subprocess.run(cmd, check=False, shell=True, capture_output=True, text=True)  # noqa: S602
    except (OSError, subprocess.CalledProcessError):
        return False
    else:
        return result.returncode == 0


def install_devhub() -> bool:
    """Install DevHub package."""
    cmd = "pip install git+https://github.com/hakimjonas/devhub.git"
    return run_command(cmd, "Installing DevHub")


def create_devhub_config() -> None:
    """Create basic DevHub configuration."""
    config_content = """# DevHub Configuration
github:
  enabled: true
  organization: "your-org"  # Update this with your GitHub organization

jira:
  enabled: true
  base_url: "https://your-company.atlassian.net"  # Update this with your Jira URL

bundle:
  max_files: 100
  include_tests: true
  include_docs: true
  claude_optimized: true

claude:
  max_context_tokens: 50000
  include_git_history: true
  include_issue_context: true
  auto_correlate_jira: true
"""

    config_path = Path.cwd() / ".devhub.yaml"
    with config_path.open("w") as f:
        f.write(config_content)


def create_setup_script() -> None:
    """Create credential setup script."""
    script_content = '''#!/usr/bin/env python3
"""Set up DevHub credentials securely."""

import asyncio
import getpass
from pathlib import Path

# Note: These imports will work after DevHub is installed
try:
    from devhub.vault import SecureVault, CredentialMetadata, CredentialType, VaultConfig
except ImportError:
    print("❌ DevHub not installed. Run: pip install git+https://github.com/hakimjonas/devhub.git")
    exit(1)


async def setup_credentials():
    """Set up secure credential storage."""

    print("🔐 DevHub Credential Setup")
    print("=" * 30)

    # Initialize vault
    vault_config = VaultConfig(
        vault_dir=Path.home() / ".devhub" / "vault"
    )
    vault = SecureVault(vault_config)

    # Get master password
    master_password = getpass.getpass("Enter master password for credential vault: ")

    try:
        await vault.initialize(master_password)
        print("✅ Vault initialized successfully")
    except Exception as e:
        print(f"❌ Vault initialization failed: {e}")
        return

    # Store GitHub token
    print("\\nFor GitHub token, go to: https://github.com/settings/tokens")
    print("Required scopes: repo, read:org, read:project")
    github_token = getpass.getpass("Enter your GitHub personal access token: ")

    if github_token:
        await vault.store_credential(
            CredentialMetadata(
                name="github_token",
                credential_type=CredentialType.API_TOKEN,
                description="GitHub personal access token for API access"
            ),
            github_token
        )
        print("✅ GitHub token stored securely")

    # Store Jira credentials
    print("\\nFor Jira token, go to: https://id.atlassian.com/manage-profile/security/api-tokens")
    jira_email = input("Enter your Jira email: ")
    jira_token = getpass.getpass("Enter your Jira API token: ")

    if jira_token and jira_email:
        await vault.store_credential(
            CredentialMetadata(
                name="jira_email",
                credential_type=CredentialType.USERNAME,
                description="Jira email for API access"
            ),
            jira_email
        )

        await vault.store_credential(
            CredentialMetadata(
                name="jira_token",
                credential_type=CredentialType.API_TOKEN,
                description="Jira API token for issue access"
            ),
            jira_token
        )
        print("✅ Jira credentials stored securely")

    print("\\n🎉 Credentials setup complete!")
    print("\\nNext steps:")
    print("1. Update .devhub.yaml with your GitHub org and Jira URL")
    print("2. Run: python get_enhanced_context.py")


if __name__ == "__main__":
    asyncio.run(setup_credentials())
'''

    script_path = Path.cwd() / "setup_devhub_credentials.py"
    with script_path.open("w") as f:
        f.write(script_content)

    # Make executable
    script_path.chmod(0o755)


def create_context_script() -> None:
    """Create enhanced context generation script."""
    script_content = '''#!/usr/bin/env python3
"""Generate enhanced Claude context using DevHub."""

import asyncio
from pathlib import Path

try:
    from devhub.claude_integration import claude_code_review_context
except ImportError:
    print("❌ DevHub not installed or credentials not set up")
    print("Run: python setup_devhub_credentials.py")
    exit(1)


async def generate_enhanced_context():
    """Generate enhanced context for Claude Code."""

    print("🧠 Generating Enhanced Claude Context")
    print("=" * 40)

    try:
        print("📋 Gathering comprehensive project context...")
        context_result = await claude_code_review_context()

        if context_result and not isinstance(context_result, Exception):
            context_file = Path("claude_enhanced_context.md")
            with open(context_file, "w") as f:
                f.write(context_result)

            print(f"✅ Enhanced context saved to: {context_file}")
            print("\\n📋 Context Preview:")
            print("-" * 50)
            print(context_result[:800] + "\\n... (truncated)")
            print("-" * 50)

            print("\\n🚀 Next Steps:")
            print("1. Copy the contents of claude_enhanced_context.md")
            print("2. Start a new Claude Code session")
            print("3. Paste the context and say:")
            print("   'This is my enhanced project context. Please help me with...'")
            print("\\n✨ Watch Claude transform into your project expert!")

        else:
            print("⚠️  Could not generate enhanced context")
            print("Make sure you've:")
            print("1. Updated .devhub.yaml with correct GitHub org and Jira URL")
            print("2. Run setup_devhub_credentials.py")
            print("3. Have proper API access to GitHub and Jira")

    except Exception as e:
        print(f"❌ Error generating context: {e}")
        print("\\n💡 Troubleshooting:")
        print("1. Check your .devhub.yaml configuration")
        print("2. Verify credentials: python setup_devhub_credentials.py")
        print("3. Test API access manually")


if __name__ == "__main__":
    asyncio.run(generate_enhanced_context())
'''

    script_path = Path.cwd() / "get_enhanced_context.py"
    with script_path.open("w") as f:
        f.write(script_content)

    # Make executable
    script_path.chmod(0o755)


def main() -> None:
    """Main setup function."""
    # Check if we're in a valid project directory
    if not check_git_repository():
        return

    project_info = detect_project_type()
    _project_name = Path.cwd().name

    for _key, _value in project_info.items():
        pass

    # Step 1: Install DevHub

    if not install_devhub():
        return

    # Step 2: Create configuration

    create_devhub_config()

    # Step 3: Create helper scripts

    create_setup_script()
    create_context_script()

    # Final instructions


if __name__ == "__main__":
    main()
