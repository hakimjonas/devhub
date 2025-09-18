#!/usr/bin/env python3
"""DevHub Professional Installer with uv.

======================================
Fast, reliable installation using uv package manager.

Usage:
    python install.py

This will guide you through the complete DevHub setup process.
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


class Colors:
    """Terminal colors for output formatting."""

    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def print_header(text: str) -> None:
    """Print a formatted header."""


def print_success(text: str) -> None:
    """Print success message."""


def print_error(text: str) -> None:
    """Print error message."""


def print_warning(text: str) -> None:
    """Print warning message."""


def print_info(text: str) -> None:
    """Print info message."""


def check_python_version() -> bool:
    """Check if Python version is 3.10 or higher."""
    required_major = 3
    required_minor = 10
    version = sys.version_info
    if version.major < required_major or (version.major == required_major and version.minor < required_minor):
        print_error(f"Python 3.10+ required. You have {version.major}.{version.minor}.{version.micro}")
        print_info("Please upgrade Python and try again.")
        return False

    print_success(f"Python version {version.major}.{version.minor}.{version.micro} ✓")
    return True


def check_uv() -> bool:
    """Check if uv is installed, install if not."""
    if shutil.which("uv") is None:
        print_info("uv not found, installing it now (this is fast!)...")

        # Install uv using the official installer
        try:
            if platform.system() == "Windows":
                # Windows installation
                subprocess.run(["powershell", "-c", "irm https://astral.sh/uv/install.ps1 | iex"], check=True)
            else:
                # Unix-like systems
                subprocess.run(["curl", "-LsSf", "https://astral.sh/uv/install.sh", "|", "sh"], shell=True, check=True)  # noqa: S602

            print_success("uv installed successfully ✓")

            # Add to PATH for current session
            home = Path.home()
            uv_path = home / ".cargo" / "bin"
            if uv_path.exists():
                os.environ["PATH"] = f"{uv_path}:{os.environ['PATH']}"

        except subprocess.CalledProcessError as e:
            print_error(f"Failed to install uv: {e}")
            print_info("Try installing manually: https://docs.astral.sh/uv/")
            return False
    else:
        print_success("uv is available ✓")

    return True


def check_git() -> bool:
    """Check if git is available."""
    if shutil.which("git") is None:
        print_warning("Git is not installed (optional but recommended)")
        print_info("Install git for full functionality: https://git-scm.com/downloads")
        return False

    print_success("Git is available ✓")
    return True


def check_devhub_directory() -> bool:
    """Check if we're in the DevHub directory."""
    current_dir = Path.cwd()

    # Check for key DevHub files
    required_files = ["pyproject.toml", "src/devhub/__init__.py"]

    for file_path in required_files:
        if not (current_dir / file_path).exists():
            print_error(f"Not in DevHub directory - missing {file_path}")
            print_info(f"Current directory: {current_dir}")
            print_info("Please run this script from the DevHub root directory")
            return False

    print_success(f"DevHub directory confirmed: {current_dir} ✓")
    return True


def setup_with_uv() -> bool | None:
    """Set up DevHub using uv."""
    print_info("Setting up Python environment with uv...")

    try:
        # Create virtual environment with uv
        subprocess.run(["uv", "venv"], check=True)
        print_success("Virtual environment created with uv ✓")

        # Sync dependencies
        print_info("Installing dependencies (this is FAST with uv!)...")
        subprocess.run(["uv", "sync", "--dev"], check=True)
        print_success("All dependencies installed ✓")

        # Install DevHub in editable mode
        print_info("Installing DevHub in development mode...")
        subprocess.run(["uv", "pip", "install", "-e", "."], check=True)
        print_success("DevHub installed successfully ✓")

    except subprocess.CalledProcessError as e:
        print_error(f"Setup failed: {e}")
        return False
    else:
        return True


def verify_installation() -> bool:
    """Verify DevHub is properly installed."""
    print_info("Verifying installation...")

    # Determine the correct Python path
    if platform.system() == "Windows":
        python_path = Path.cwd() / ".venv" / "Scripts" / "python"
    else:
        python_path = Path.cwd() / ".venv" / "bin" / "python"

    # Test import
    try:
        test_code = """
from devhub.sdk import DevHubClient
from devhub.vault import SecureVault
from devhub.claude_integration import get_claude_enhancer
print('Import successful')
"""
        result = subprocess.run([str(python_path), "-c", test_code], check=False, capture_output=True, text=True)

        if result.returncode == 0 and "Import successful" in result.stdout:
            print_success("DevHub imports correctly ✓")
        else:
            print_error(f"Import test failed: {result.stderr}")
            return False

    except (ImportError, ModuleNotFoundError) as e:
        print_error(f"Import verification failed: {e}")
        return False

    return True


def create_example_scripts() -> None:
    """Create helpful example scripts for users."""
    examples_dir = Path.cwd() / "examples"

    # Create setup_project.py for existing projects
    setup_script = '''#!/usr/bin/env python3
"""Quick setup for using DevHub in your existing project."""

import asyncio
import yaml
from pathlib import Path

def create_config():
    """Create a basic DevHub configuration."""
    config = {
        "version": "1.0",
        "github": {
            "enabled": True,
            "organization": input("GitHub organization (or press Enter to skip): ") or "your-org"
        },
        "jira": {
            "enabled": True,
            "base_url": input("Jira URL (e.g., https://company.atlassian.net): ") or "https://your-company.atlassian.net"
        },
        "bundle": {
            "max_files": 100,
            "include_tests": True,
            "include_docs": True,
            "claude_optimized": True
        }
    }

    config_path = Path.cwd() / ".devhub.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)

    print(f"✅ Configuration saved to {config_path}")
    print("📝 You can edit this file later to update settings")

if __name__ == "__main__":
    print("🚀 DevHub Quick Setup for Your Project")
    print("=" * 40)
    create_config()
    print("\\n✅ Setup complete! Next steps:")
    print("1. Run: python setup_credentials.py")
    print("2. Run: python generate_context.py")
'''

    (examples_dir / "setup_project.py").write_text(setup_script)
    print_success("Created example setup script ✓")


def print_next_steps() -> None:
    """Print instructions for next steps."""
    print_header("Installation Complete!")

    if platform.system() == "Windows":
        pass


def _run_installation_checks() -> bool:
    """Run all pre-installation checks."""
    checks = [check_python_version, check_uv, check_devhub_directory]
    return all(check() for check in checks)


def main() -> int:
    """Main installation process."""
    print_header("DevHub Professional Installer (uv)")

    # System checks with early exit
    if not _run_installation_checks():
        return 1

    check_git()  # Optional check

    # Installation process
    if not setup_with_uv():
        print_error("Installation failed")
        print_info("Troubleshooting:")
        return 1

    # Post-installation steps (verification warnings are non-fatal)
    if not verify_installation():
        print_warning("Verification had issues but installation may still work")

    create_example_scripts()
    print_next_steps()
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        sys.exit(1)
    except (OSError, subprocess.CalledProcessError, RuntimeError) as e:
        print_error(f"Unexpected error: {e}")
        print_info("Please report this issue with the full error message")
        sys.exit(1)
