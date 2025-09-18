#!/usr/bin/env python3
"""DevHub Global Installer (Cross-platform).

Professional installation as a global command-line tool.
"""

import builtins
import contextlib
import os
import shutil
import subprocess
import sys
from pathlib import Path


class Installer:
    """Professional DevHub installer."""

    def __init__(self) -> None:
        """Initialize the installer with project path."""
        self.devhub_path = Path(__file__).parent
        self.install_method: str | None = None

    def print_header(self, text: str) -> None:
        """Print formatted header."""

    def check_python(self) -> None:
        """Check Python version."""
        required_major = 3
        required_minor = 10
        version = sys.version_info
        if version.major < required_major or (version.major == required_major and version.minor < required_minor):
            sys.exit(1)

    def detect_tools(self) -> list[tuple[str, str]]:
        """Detect available installation tools."""
        tools = []

        if shutil.which("uv"):
            tools.append(("uv", "Ultra-fast Python package installer"))

        if shutil.which("pipx"):
            tools.append(("pipx", "Install Python apps in isolated environments"))

        # pip is always available with Python
        tools.append(("pip", "Standard Python package installer"))

        return tools

    def choose_method(self, tools: list[tuple[str, str]]) -> None:
        """Let user choose installation method."""
        if len(tools) == 1:
            self.install_method = tools[0][0]
            return

        for _i, (_tool, _desc) in enumerate(tools, 1):
            pass

        while True:
            try:
                choice = input(f"\nChoose method (1-{len(tools)}): ")
                idx = int(choice) - 1
                if 0 <= idx < len(tools):
                    self.install_method = tools[idx][0]
                    break
            except (ValueError, IndexError):
                pass

    def install_tool(self, tool: str) -> None:
        """Install a missing tool."""
        if tool == "uv":
            if sys.platform == "win32":
                # Windows
                subprocess.run(["powershell", "-c", "irm https://astral.sh/uv/install.ps1 | iex"], check=False)
            else:
                # Unix-like
                subprocess.run("curl -LsSf https://astral.sh/uv/install.sh | sh", check=False, shell=True)  # noqa: S602

        elif tool == "pipx":
            subprocess.run([sys.executable, "-m", "pip", "install", "--user", "pipx"], check=False)
            subprocess.run([sys.executable, "-m", "pipx", "ensurepath"], check=False)

    def install_devhub(self) -> None:
        """Install DevHub using selected method."""
        try:
            if self.install_method == "uv":
                # Install as a tool with uv
                subprocess.run(["uv", "tool", "install", "--from", str(self.devhub_path), "devhub"], check=True)

            elif self.install_method == "pipx":
                # Install with pipx
                subprocess.run(["pipx", "install", str(self.devhub_path)], check=True)

            else:  # pip
                # Install with pip --user
                subprocess.run([sys.executable, "-m", "pip", "install", "--user", str(self.devhub_path)], check=True)

                # Check PATH
                user_bin = Path.home() / ".local" / "bin"
                if str(user_bin) not in os.environ.get("PATH", ""):
                    if sys.platform == "win32":
                        pass
                    else:
                        pass

        except subprocess.CalledProcessError:
            sys.exit(1)

    def verify_installation(self) -> None:
        """Verify DevHub is installed and working."""
        if shutil.which("devhub"):
            # Try to get version
            with contextlib.suppress(builtins.BaseException):
                subprocess.run(["devhub", "--version"], check=False, capture_output=True, text=True)
        else:
            pass

    def print_next_steps(self) -> None:
        """Print next steps for the user."""
        self.print_header("Installation Complete!")

    def run(self) -> None:
        """Run the installation process."""
        self.print_header("DevHub Professional Installer")

        # Check Python
        self.check_python()

        # Detect available tools
        tools = self.detect_tools()

        # Special handling for optimal tool selection
        if not shutil.which("uv") and not shutil.which("pipx") and input("Install uv now? (y/n): ").lower() == "y":
            self.install_tool("uv")
            tools = self.detect_tools()

        # Choose installation method
        self.choose_method(tools)

        # Install DevHub
        self.install_devhub()

        # Verify
        self.verify_installation()

        # Next steps
        self.print_next_steps()


if __name__ == "__main__":
    try:
        installer = Installer()
        installer.run()
    except KeyboardInterrupt:
        sys.exit(1)
    except (OSError, subprocess.CalledProcessError, RuntimeError):
        sys.exit(1)
