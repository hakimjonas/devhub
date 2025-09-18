# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## CRITICAL: Working Principles

**NEVER celebrate prematurely. NEVER be dishonest about the state of the code.**

### Mandatory Quality Checks - ALWAYS RUN THESE:

```bash
# CRITICAL: ALWAYS use uv run - NEVER use global python/tools
# The user may have other Python environments active that will give wrong results

# 1. ALWAYS run on entire project (.) not just src/
uv run ruff check .          # MUST be 0 errors
uv run ruff format .         # MUST format everything
uv run mypy .               # MUST be 0 errors
uv run pytest              # MUST be 100% pass rate

# NEVER run: python, mypy, ruff, pytest directly - always prefix with "uv run"
```

### Assessment Principles:

1. **Base assessments on ACTUAL CODE, not project descriptions**
2. **Run quality checks BEFORE making any claims about code quality**
3. **Never declare victory until ALL checks pass on entire project**
4. **If you find basic violations (like `if/else` blocks), admit the code is NOT exemplary**
5. **Be honest about technical debt and architectural issues**

### Working Standards:

- **ALWAYS use "uv run" prefix** - never run python/mypy/ruff/pytest directly
- User may have other Python environments active that give different results
- No premature optimization of token usage at expense of thoroughness
- Always verify claims with actual tool output from uv-managed environment
- Report actual numbers, not aspirational ones
- Acknowledge when work is incomplete
- Never use celebration language until everything actually passes

## Core Commands

### Development
```bash
# Install dependencies (using uv - the modern Python package manager)
uv sync

# Run the main CLI
uv run devhub --version
uv run devhub doctor
uv run devhub bundle --jira-key PROJ-123

# Run MCP server
uv run devhub-mcp --help
```

### Testing
```bash
# Run all tests with coverage
uv run pytest

# Run specific test categories
uv run pytest -m unit
uv run pytest -m integration
uv run pytest -m property
uv run pytest -m slow

# Run tests in parallel
uv run pytest -n auto

# Run a specific test file
uv run pytest tests/test_main.py

# Run a specific test
uv run pytest tests/test_main.py::test_specific_function
```

### Code Quality
```bash
# Type checking - MUST pass on ENTIRE project
uv run mypy .
uv run pyright .

# Linting and formatting - MUST run on ENTIRE project
uv run ruff check .
uv run ruff format .

# Security scanning
uv run bandit -r src/devhub
uv run semgrep --config=auto src/devhub

# Dead code detection
uv run vulture src/devhub
```

### Pre-commit
```bash
# Install pre-commit hooks
uv run pre-commit install

# Run all pre-commit hooks manually
uv run pre-commit run --all-files
```

## Architecture Overview

DevHub is a **functional programming exemplar** demonstrating clean Python code through immutable data structures, pure functions, and comprehensive type safety. The codebase strictly adheres to FP principles.

### Key Components

1. **Main Entry Point** (`src/devhub/main.py`)
   - CLI interface using argparse
   - Commands: `bundle` (main functionality), `doctor` (health check)
   - All domain models are frozen dataclasses (JiraIssue, Repository, PullRequest, ReviewComment)
   - Uses `returns.Result` for error handling instead of exceptions

2. **Configuration** (`src/devhub/config.py`)
   - Hierarchical configuration system (environment → config file → defaults)
   - Organization-first multi-tenant support
   - Immutable `DevHubConfig` dataclass
   - Config locations: `~/.config/devhub/config.toml` or environment variables

3. **SDK** (`src/devhub/sdk.py`)
   - Async-first `DevHubClient` for programmatic access
   - Immutable `ContextRequest` and `BundleContext` dataclasses
   - All operations return `Result[T, str]` for explicit error handling
   - Pure functions for data transformation

4. **MCP Server** (`src/devhub/mcp_server.py`)
   - Model Context Protocol server for AI agents (Claude Desktop)
   - Tools: get-bundle-context, get-jira-issue, get-pr-details, get-pr-comments
   - Async JSON-RPC implementation

### Functional Programming Principles

- **Immutability**: ALL data structures are frozen dataclasses with `frozen=True, slots=True`
- **Pure Functions**: Functions have no side effects when possible, I/O is isolated
- **Result Types**: Uses `returns.Result` for error handling, avoiding exceptions
- **Type Safety**: 100% type coverage with strict mypy and pyright compliance
- **No Mutations**: Collections use tuple/frozenset, transformations return new instances

### External Dependencies

- **GitHub Operations**: Uses `gh` CLI (must be authenticated)
- **Git Operations**: Direct subprocess calls to `git`
- **Jira API**: Direct HTTP requests with basic auth
- **FP Libraries**: `returns`, `toolz`, `attrs`, `immutables`, `cattrs`

## Testing Strategy

- **Coverage**: 92.89% test coverage, target >90%
- **Property-Based**: Uses Hypothesis for testing pure functions
- **Test Organization**:
  - Unit tests: Pure function testing
  - Integration tests: End-to-end workflows
  - Property tests: Invariant validation
  - Slow tests: Performance-sensitive operations

## Code Style Requirements

- **Type Annotations**: EVERY function, method, and variable must have explicit types
- **Docstrings**: Google-style for all public functions/classes
- **Line Length**: 120 characters maximum
- **Import Style**: Single-line imports, alphabetically sorted
- **Ruff Rules**: ALL rules enabled (`select = ["ALL"]`) with minimal exceptions

## Common Development Tasks

When implementing new features:
1. Define immutable domain models as frozen dataclasses
2. Implement business logic as pure functions returning Result types
3. Isolate I/O operations in dedicated functions
4. Add comprehensive tests including property-based tests
5. Ensure mypy and pyright pass in strict mode
6. Document with Google-style docstrings

When modifying existing code:
1. Maintain immutability - never mutate existing data structures
2. Use `dataclasses.replace()` for creating modified versions
3. Preserve functional style - avoid classes with state
4. Keep functions pure when possible
5. Maintain >90% test coverage