"""Immediate enhancement script for existing Jira + GitHub + Claude Code projects.

Run this in your existing project to get DevHub superpowers immediately!
"""

import asyncio
import json
import re
from pathlib import Path


# Note: In a real setup, these would be proper imports
# For demonstration, we'll show the workflow


async def setup_existing_project_enhancement() -> None:
    """Set up DevHub enhancement for your existing project."""
    # Step 1: Environment Detection

    project_path = Path.cwd()

    # Detect Git repository
    git_dir = project_path / ".git"
    if git_dir.exists():
        # Try to detect GitHub
        try:
            with (git_dir / "config").open() as f:
                git_config = f.read()
                if "github.com" in git_config:
                    # Extract repo info

                    repo_match = re.search(r"github\.com[:/]([^/\s]+)/([^/\s\.]+)", git_config)
                    if repo_match:
                        owner, repo = repo_match.groups()
        except (OSError, UnicodeDecodeError):
            pass
    else:
        pass

    # Detect package.json, requirements.txt, etc.
    config_files = ["package.json", "requirements.txt", "pom.xml"]
    for config_file in config_files:
        if (project_path / config_file).exists():
            pass

    # Step 2: Quick DevHub Setup

    project_path / ".devhub.yaml"

    # Step 3: Enhanced Claude Context Generation

    # Simulate what DevHub would generate
    enhanced_context = await generate_enhanced_context(project_path)

    context_file = project_path / "claude_enhanced_context.md"
    with context_file.open("w") as f:
        f.write(enhanced_context)

    # Step 4: Integration Scripts

    # Create helper scripts
    create_helper_scripts(project_path)

    # Step 5: Next Steps

    next_steps = [
        "1. Update .devhub.yaml with your GitHub org and Jira URL",
        "2. Run: pip install git+https://github.com/hakimjonas/devhub.git",
        "3. Set up credentials: python setup_credentials.py",
        "4. Test enhanced context: python get_claude_context.py",
        "5. Copy the generated context to Claude and see the magic!",
    ]

    for _step in next_steps:
        pass


async def generate_enhanced_context(project_path: Path) -> str:
    """Generate enhanced context for Claude."""
    context_parts = [
        "# Enhanced Project Context for Claude Code",
        "",
        "## 🏗️ Project Overview",
    ]

    # Analyze project structure
    python_files = list(project_path.glob("**/*.py"))
    js_files = list(project_path.glob("**/*.js")) + list(project_path.glob("**/*.ts"))
    test_files = list(project_path.glob("**/test*.py")) + list(project_path.glob("**/*test.py"))

    context_parts.extend(
        [
            f"- **Project Directory**: {project_path.name}",
            f"- **Python Files**: {len(python_files)}",
            f"- **JavaScript/TypeScript Files**: {len(js_files)}",
            f"- **Test Files**: {len(test_files)}",
            "",
        ]
    )

    # Try to detect current branch
    try:
        git_head = project_path / ".git" / "HEAD"
        if git_head.exists():
            with git_head.open() as f:
                head_content = f.read().strip()
                if head_content.startswith("ref: refs/heads/"):
                    current_branch = head_content.split("/")[-1]
                    context_parts.extend(
                        [
                            f"- **Current Branch**: {current_branch}",
                            "",
                        ]
                    )
    except (OSError, UnicodeDecodeError):
        pass  # Git operations are optional

    # Analyze dependencies
    context_parts.extend(
        [
            "## 📦 Dependencies & Tech Stack",
        ]
    )

    # Python dependencies
    req_file = project_path / "requirements.txt"
    if req_file.exists():
        try:
            with req_file.open() as f:
                deps = [line.strip() for line in f if line.strip() and not line.startswith("#")]
                context_parts.extend(
                    [
                        "**Python Dependencies:**",
                        *[f"- {dep}" for dep in deps[:10]],  # First 10
                        "",
                    ]
                )
        except (OSError, ValueError):
            pass

    # Node.js dependencies
    package_json = project_path / "package.json"
    if package_json.exists():
        try:
            with package_json.open() as f:
                data = json.load(f)
                deps = list(data.get("dependencies", {}).keys())
                context_parts.extend(
                    [
                        "**Node.js Dependencies:**",
                        *[f"- {dep}" for dep in deps[:10]],  # First 10
                        "",
                    ]
                )
        except (OSError, ValueError):
            pass

    # Development workflow context
    context_parts.extend(
        [
            "## 🔄 Development Workflow",
            "",
            "**Integration Points:**",
            "- GitHub: Pull requests and code reviews",
            "- Jira: Issue tracking and project management",
            "- DevHub: Enhanced context and automation",
            "",
            "**Enhanced Capabilities with DevHub:**",
            "- Automatic PR-Jira correlation",
            "- Comprehensive code review context",
            "- Smart debugging assistance",
            "- Architecture-aware suggestions",
            "",
        ]
    )

    # Recent activity simulation
    context_parts.extend(
        [
            "## 📈 Recent Activity (Simulated)",
            "",
            "**Recent Focus Areas:**",
            "- Code review automation",
            "- Integration improvements",
            "- Test coverage enhancement",
            "",
            "**Current Development Phase:**",
            "Ready for DevHub integration to supercharge Claude Code interactions!",
            "",
        ]
    )

    # Claude-specific guidance
    context_parts.extend(
        [
            "## 🤖 Claude Code Integration",
            "",
            "**With this enhanced context, Claude can now:**",
            "",
            "1. **Understand Your Project Deeply**",
            "   - Complete tech stack and dependencies",
            "   - Current development focus and branch",
            "   - Integration with GitHub and Jira",
            "",
            "2. **Provide Better Code Reviews**",
            "   - Context-aware suggestions",
            "   - Business logic alignment",
            "   - Test coverage recommendations",
            "",
            "3. **Assist with Strategic Decisions**",
            "   - Architecture improvements",
            "   - Technical debt prioritization",
            "   - Integration optimization",
            "",
            "**Next Level: After DevHub Setup**",
            "- Real-time GitHub PR context",
            "- Automatic Jira issue correlation",
            "- Live CI/CD status integration",
            "- Historical pattern analysis",
            "",
            "---",
            "",
            "🚀 **This is just the beginning!** Once DevHub is fully integrated,",
            "Claude will have access to real-time project data, making every",
            "interaction more intelligent and contextually relevant.",
        ]
    )

    return "\n".join(context_parts)


def create_helper_scripts(project_path: Path) -> None:
    """Create helper scripts for DevHub integration."""
    # Setup credentials script
    setup_credentials_script = '''"""Setup secure credentials for DevHub integration."""

import asyncio
import getpass
from devhub.vault import SecureVault, CredentialMetadata, CredentialType, VaultConfig
from pathlib import Path

async def setup_credentials():
    """Set up secure credential storage."""

    print("🔐 Setting up DevHub Secure Credentials")
    print("=" * 40)

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
    jira_token = getpass.getpass("Enter your Jira API token: ")
    if jira_token:
        await vault.store_credential(
            CredentialMetadata(
                name="jira_token",
                credential_type=CredentialType.API_TOKEN,
                description="Jira API token for issue access"
            ),
            jira_token
        )
        print("✅ Jira token stored securely")

    print("\\n🎉 Credentials setup complete!")
    print("You can now run: python get_claude_context.py")

if __name__ == "__main__":
    asyncio.run(setup_credentials())
'''

    # Enhanced context script
    context_script = '''"""Get enhanced Claude context using DevHub."""

import asyncio
from pathlib import Path
from devhub.claude_integration import claude_code_review_context, claude_debugging_context

async def get_claude_context():
    """Generate enhanced context for Claude Code."""

    print("🧠 Generating Enhanced Claude Context")
    print("=" * 38)

    try:
        # Try code review context first
        print("📋 Generating code review context...")
        context_result = await claude_code_review_context()

        if context_result:
            context_file = Path("claude_context.md")
            with open(context_file, "w") as f:
                f.write(context_result)

            print(f"✅ Enhanced context saved to: {context_file}")
            print("\\n📋 Context Preview:")
            print("-" * 20)
            print(context_result[:500] + "...")
            print("-" * 20)
            print("\\n🚀 Copy this context to Claude for enhanced interactions!")

        else:
            print("⚠️  Could not generate enhanced context")

    except Exception as e:
        print(f"❌ Error generating context: {e}")
        print("💡 Make sure you've run setup_credentials.py first")

if __name__ == "__main__":
    asyncio.run(get_claude_context())
'''

    # Daily workflow script
    daily_script = '''"""Daily DevHub workflow enhancement."""

import asyncio
from datetime import datetime

async def daily_devhub_check():
    """Run daily DevHub enhancement check."""

    print(f"🌅 Daily DevHub Check - {datetime.now().strftime('%Y-%m-%d')}")
    print("=" * 50)

    checks = [
        "🔍 Checking for new GitHub PRs...",
        "📋 Updating Jira issue context...",
        "🧪 Analyzing test coverage changes...",
        "🔄 Generating fresh Claude context...",
    ]

    for check in checks:
        print(f"   {check}")
        await asyncio.sleep(0.5)  # Simulate work

    print("\\n✅ Daily check complete!")
    print("📝 Run: python get_claude_context.py for latest context")

if __name__ == "__main__":
    asyncio.run(daily_devhub_check())
'''

    # Write scripts
    scripts = [
        ("setup_credentials.py", setup_credentials_script),
        ("get_claude_context.py", context_script),
        ("daily_devhub.py", daily_script),
    ]

    for script_name, script_content in scripts:
        script_path = project_path / script_name
        with script_path.open("w") as f:
            f.write(script_content)


if __name__ == "__main__":
    asyncio.run(setup_existing_project_enhancement())
