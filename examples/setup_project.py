#!/usr/bin/env python3
"""Quick setup for using DevHub in your existing project."""

from pathlib import Path

import yaml


def create_config() -> None:
    """Create a basic DevHub configuration."""
    config = {
        "version": "1.0",
        "github": {
            "enabled": True,
            "organization": input("GitHub organization (or press Enter to skip): ") or "your-org",
        },
        "jira": {
            "enabled": True,
            "base_url": input("Jira URL (e.g., https://company.atlassian.net): ")
            or "https://your-company.atlassian.net",
        },
        "bundle": {"max_files": 100, "include_tests": True, "include_docs": True, "claude_optimized": True},
    }

    config_path = Path.cwd() / ".devhub.yaml"
    with config_path.open("w") as f:
        yaml.dump(config, f, default_flow_style=False)


if __name__ == "__main__":
    create_config()
