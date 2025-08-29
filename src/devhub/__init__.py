"""DevHub - CLI tool to bundle Jira tickets, GitHub PRs, diffs, and comments for code review.

This package provides a command-line interface for gathering and bundling development
context from Jira and GitHub for efficient code review workflows.
"""

__version__ = "0.1.0"
__author__ = "hakimjonas"
__email__ = "your.email@example.com"

# Re-export main components for easy importing
from devhub.config import DevHubConfig
from devhub.config import load_config
from devhub.config import load_config_with_environment


__all__ = [
    "DevHubConfig",
    "__version__",
    "load_config",
    "load_config_with_environment",
]
