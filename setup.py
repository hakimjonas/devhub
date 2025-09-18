#!/usr/bin/env python3
"""Setup script for DevHub - Professional installation support."""

from pathlib import Path

from setuptools import find_packages
from setuptools import setup


# Read the README file
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

setup(
    name="devhub",
    version="0.1.0",
    author="DevHub Team",
    description="Unified development platform integration for enhanced Claude Code workflows",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.10",
    install_requires=[
        "aiohttp>=3.8.0",
        "pyyaml>=6.0",
        "click>=8.1.0",
        "cryptography>=41.0.0",
        "prometheus-client>=0.17.0",
        "returns>=0.22.0",
        "pydantic>=2.0.0",
        "rich>=13.0.0",
        "typing-extensions>=4.7.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.1.0",
            "mypy>=1.5.0",
            "ruff>=0.1.0",
            "black>=23.0.0",
            "pre-commit>=3.3.0",
        ],
        "test": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.1.0",
            "hypothesis>=6.80.0",
            "mutmut>=2.4.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "devhub=devhub.cli:main",
            "devhub-mcp=devhub.mcp.server:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
