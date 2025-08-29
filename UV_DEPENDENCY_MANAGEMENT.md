# Modern Dependency Management with UV

This guide demonstrates UV's modern tools for efficient dependency management, addressing the pain point of manually updating dependencies one by one.

## Overview

UV provides comprehensive dependency management tools that go far beyond traditional pip workflows:

- **Automated dependency resolution and locking**
- **Bulk dependency updates**
- **Dependency tree visualization**
- **Environment synchronization**
- **Modern project management**

## Key UV Commands for Dependency Management

### 1. Dependency Visualization

```bash
# View complete dependency tree with versions
uv tree

# Export dependency information in different formats
uv export --format requirements-txt > requirements.txt
uv export --format pip-freeze > freeze.txt
```

### 2. Adding Dependencies

```bash
# Add production dependency
uv add requests

# Add development dependency
uv add pytest --dev

# Add dependency with version constraints
uv add "django>=4.0,<5.0"

# Add dependency from git repository
uv add git+https://github.com/user/repo.git
```

### 3. Updating Dependencies

```bash
# Update all dependencies to latest compatible versions
uv sync --upgrade

# Update specific dependency
uv add package@latest

# Update dev dependencies only
uv sync --group dev --upgrade

# Force update to latest versions (may break compatibility)
uv sync --upgrade-package package-name
```

### 4. Removing Dependencies

```bash
# Remove dependency
uv remove requests

# Remove dev dependency
uv remove pytest --dev
```

### 5. Lock File Management

```bash
# Update lock file without installing
uv lock

# Update lock file and install
uv sync

# Install from lock file exactly (CI/CD usage)
uv sync --frozen
```

## Modern Workflows

### Bulk Dependency Updates (Solving the PyCharm Pain Point)

Instead of updating dependencies one by one in PyCharm:

```bash
# Method 1: Update all dependencies at once
uv sync --upgrade

# Method 2: Check what would be updated first
uv lock --upgrade --dry-run

# Method 3: Update specific groups
uv sync --group dev --upgrade
uv sync --group test --upgrade
```

### Dependency Audit and Security

```bash
# Show outdated dependencies
uv tree --outdated

# Check for security vulnerabilities (using safety from our dev deps)
uv run safety check

# Update only security patches
uv sync --upgrade --only-patches
```

### Environment Management

```bash
# Sync environment to match lock file exactly
uv sync

# Sync with specific extras
uv sync --extra dev --extra test

# Clean sync (remove unused packages)
uv sync --exact
```

### Project Initialization and Migration

```bash
# Initialize new UV project
uv init my-project

# Add UV to existing project
uv init --lib  # for library
uv init --app  # for application

# Migrate from requirements.txt
uv add -r requirements.txt
```

## Advanced Features

### 1. Dependency Groups

Our project uses dependency groups for better organization:

```toml
[tool.uv]
dev-dependencies = [
    "pytest>=8.3.4",
    "ruff>=0.8.4",
    "mypy>=1.13.0",
    # ... more dev tools
]
```

Manage groups separately:
```bash
uv sync --group dev      # Install only dev dependencies
uv sync --no-group dev   # Install without dev dependencies
```

### 2. Version Management

```bash
# Pin to exact version
uv add "package==1.2.3"

# Use version ranges
uv add "package>=1.0,<2.0"

# Update within constraints
uv sync --upgrade
```

### 3. Platform-Specific Dependencies

```bash
# Add platform-specific dependency
uv add "pywin32; sys_platform == 'win32'"

# Add Python version specific
uv add "typing-extensions; python_version < '3.8'"
```

## Integration with Development Tools

### Pre-commit Integration

```bash
# Install pre-commit hooks
uv run pre-commit install

# Run hooks manually
uv run pre-commit run --all-files
```

### Running Tools

```bash
# Run tests
uv run pytest

# Run linting
uv run ruff check src/
uv run ruff format src/

# Run type checking
uv run mypy src/

# Run any installed tool
uv run bandit -r src/
```

## Comparison: Old vs New Workflow

### Old Workflow (Manual PyCharm Updates)
1. Open PyCharm
2. Go to Project Settings → Python Interpreter
3. Click on each outdated package individually
4. Click "Upgrade" for each one
5. Wait for each update to complete
6. Repeat for 20+ packages
7. Hope nothing breaks

### New UV Workflow
```bash
# See what's outdated
uv tree

# Update everything at once
uv sync --upgrade

# Or update selectively
uv add package@latest  # for specific packages
```

## Best Practices

1. **Always use lock files**: Commit `uv.lock` to ensure reproducible builds
2. **Group dependencies**: Separate dev, test, and production dependencies
3. **Regular updates**: Run `uv sync --upgrade` regularly, not just when forced
4. **Check before updating**: Use `uv lock --upgrade --dry-run` to see changes
5. **Test after updates**: Run your test suite after bulk updates
6. **Use constraints**: Pin major versions to avoid breaking changes

## Common UV Commands Cheat Sheet

| Task | Command |
|------|---------|
| Install all dependencies | `uv sync` |
| Update all dependencies | `uv sync --upgrade` |
| Add new dependency | `uv add package` |
| Add dev dependency | `uv add package --dev` |
| Remove dependency | `uv remove package` |
| Show dependency tree | `uv tree` |
| Update lock file | `uv lock` |
| Export requirements | `uv export --format requirements-txt` |
| Run command in environment | `uv run command` |
| Check for outdated | `uv tree --outdated` (if supported) |

## Benefits Over Traditional Methods

1. **Speed**: UV is written in Rust and extremely fast
2. **Reliability**: Better dependency resolution than pip
3. **Reproducibility**: Lock files ensure consistent environments
4. **Modern tooling**: Built-in support for modern Python packaging
5. **Workspace support**: Multi-package project support
6. **Better error messages**: Clear feedback when things go wrong
7. **Bulk operations**: Update many packages at once safely

## FAQ and Troubleshooting

### Why didn't `uv sync --upgrade` change my `pyproject.toml`?
- `pyproject.toml` declares constraints (e.g., `attrs>=24.2.0`).
- Exact versions are pinned in `uv.lock`.
- `uv sync --upgrade` refreshes `uv.lock` to newer versions that still satisfy the constraints, then installs them. It does not rewrite your constraints.

If you want to change the constraints in `pyproject.toml` (e.g., adopt the latest as your new minimum), do one of the following:

```bash
# Bump a single dependency to latest and record it in pyproject
uv add attrs@latest

# Bump multiple explicitly
uv add attrs@latest cattrs@latest returns@latest

# Or edit pyproject constraints manually, then refresh the lock
uv lock --upgrade && uv sync
```

To preview what would change without installing:
```bash
uv lock --upgrade --dry-run
```

### I upgraded `pip` with `uv pip install --upgrade pip` but `uv sync` uninstalled it. Why?
- `uv sync` makes your environment match `uv.lock` exactly.
- Anything not declared in the project (and thus not present in `uv.lock`) is considered extraneous and is removed.
- `pip` isn’t a declared dependency in this project, so `uv sync` removes it.

You generally don’t need `pip` inside a UV-managed project: UV has its own resolver/installer and `uv add/remove/sync` replace pip workflows.

If you absolutely must keep `pip` for a tool that invokes it, add it as a dev dependency so it’s tracked in the lock:

```toml
# pyproject.toml
[tool.uv]
dev-dependencies = [
    # ...existing dev deps...
    "pip>=25.2",
]
```

Then run:
```bash
uv sync --group dev
```

Otherwise, treat `uv pip ...` installs as ephemeral — `uv sync` will clean them up.

### Quick recipes
```bash
# Update all project deps within current constraints
uv sync --upgrade

# Update only a specific package
uv sync --upgrade-package attrs

# Promote current latest versions to pyproject constraints
uv add attrs@latest cattrs@latest

# See planned upgrades without changing the env
uv lock --upgrade --dry-run
```
