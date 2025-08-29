# DevHub Configuration Guide

> **Complete guide to DevHub's hierarchical configuration system**

DevHub's configuration system is designed around **immutable data structures** and **functional principles**, providing flexible, type-safe configuration management for multi-organization environments.

## Configuration Architecture

### Hierarchical Loading System

DevHub searches for configuration files in the following order:

1. **Project-local**: `.devhub.json` (highest priority)
2. **User-specific**: `~/.devhub/config.json`
3. **System-wide**: `/etc/devhub/config.json` (Unix/Linux only)
4. **Environment variables**: Override specific values
5. **Built-in defaults**: Fallback for any unspecified values

### Configuration Merging Strategy

Configuration follows a **functional composition** pattern where more specific settings override general ones:

```
System Config → User Config → Project Config → Environment Variables
```

Each level can provide partial configuration; missing values cascade from more general sources.

## Configuration Schema

### Root Configuration Structure

```json
{
  "config_version": "1.0",
  "default_organization": "organization-name",
  "organizations": {
    "org-name": "Organization configuration object"
  },
  "global_jira": "Global Jira settings object",
  "global_github": "Global GitHub settings object",
  "global_output": "Global output settings object"
}
```

### Organization Configuration

Each organization represents a complete working context:

```json
{
  "name": "my-company",
  "description": "Human-readable description",
  "jira": {
    "base_url": "https://mycompany.atlassian.net",
    "default_project_prefix": "PROJ",
    "email": null,
    "api_token": null,
    "timeout_seconds": 30,
    "max_retries": 3
  },
  "github": {
    "default_org": "my-github-org",
    "timeout_seconds": 30,
    "max_retries": 3,
    "use_ssh": false
  },
  "output": {
    "base_directory": "review-bundles",
    "include_timestamps": true,
    "file_permissions": 644,
    "directory_permissions": 755
  },
  "bundle_defaults": {
    "include_jira": true,
    "include_pr": true,
    "include_diff": true,
    "include_comments": true,
    "comment_limit": 10,
    "diff_context_lines": 3
  }
}
```

## Configuration Examples

### Single Organization Setup

For simple, single-company usage:

```json
{
  "config_version": "1.0",
  "default_organization": "acme-corp",
  "organizations": {
    "acme-corp": {
      "description": "ACME Corporation",
      "jira": {
        "base_url": "https://acme.atlassian.net",
        "default_project_prefix": "ACME"
      },
      "github": {
        "default_org": "acme-corp"
      },
      "bundle_defaults": {
        "comment_limit": 15,
        "include_diff": true
      }
    }
  }
}
```

### Multi-Client Consultant Setup

For consultants working with multiple clients:

```json
{
  "config_version": "1.0",
  "default_organization": "client-alpha",
  "organizations": {
    "client-alpha": {
      "description": "Client Alpha - E-commerce Platform",
      "jira": {
        "base_url": "https://alpha.atlassian.net",
        "default_project_prefix": "ECOM",
        "timeout_seconds": 45
      },
      "github": {
        "default_org": "alpha-ecommerce",
        "use_ssh": true
      },
      "output": {
        "base_directory": "alpha-reviews"
      }
    },
    "client-beta": {
      "description": "Client Beta - Financial Services",
      "jira": {
        "base_url": "https://beta-finance.atlassian.net",
        "default_project_prefix": "FIN"
      },
      "github": {
        "default_org": "beta-fintech"
      },
      "output": {
        "base_directory": "beta-reviews"
      },
      "bundle_defaults": {
        "comment_limit": 25,
        "diff_context_lines": 5
      }
    },
    "internal": {
      "description": "Internal Tools and Utilities",
      "github": {
        "default_org": "my-consulting-firm"
      },
      "bundle_defaults": {
        "include_jira": false
      }
    }
  },
  "global_jira": {
    "timeout_seconds": 60,
    "max_retries": 5
  }
}
```

### Open Source Project Setup

For open source projects without Jira:

```json
{
  "config_version": "1.0",
  "default_organization": "oss-project",
  "organizations": {
    "oss-project": {
      "description": "Open Source Project",
      "github": {
        "default_org": "my-oss-org"
      },
      "bundle_defaults": {
        "include_jira": false,
        "comment_limit": 20
      },
      "output": {
        "base_directory": "pr-reviews"
      }
    }
  }
}
```

## Environment Variable Integration

### Credential Management

**Never store credentials in configuration files**. Use environment variables:

```bash
# Jira Authentication
export JIRA_EMAIL="your-email@company.com"
export JIRA_API_TOKEN="your-api-token"

# Optional: Override organization
export DEVHUB_ORGANIZATION="client-alpha"

# Optional: Enable debug logging
export DEVHUB_DEBUG="1"
```

### Dynamic Configuration Override

Environment variables can override specific configuration values:

```bash
# Override timeout for current session
export JIRA_TIMEOUT_SECONDS="90"
export GITHUB_TIMEOUT_SECONDS="60"

# Override default comment limit
export BUNDLE_COMMENT_LIMIT="30"

# Override output directory
export BUNDLE_OUTPUT_DIR="/tmp/reviews"
```

## Advanced Configuration Patterns

### Configuration Composition

Create modular configurations by composing smaller files:

**Base configuration** (`~/.devhub/config.json`):
```json
{
  "config_version": "1.0",
  "global_jira": {
    "timeout_seconds": 60,
    "max_retries": 3
  },
  "global_output": {
    "file_permissions": 644,
    "directory_permissions": 755
  }
}
```

**Project-specific** (`.devhub.json`):
```json
{
  "default_organization": "this-project",
  "organizations": {
    "this-project": {
      "jira": {
        "base_url": "https://project.atlassian.net",
        "default_project_prefix": "PROJ"
      },
      "github": {
        "default_org": "project-org"
      }
    }
  }
}
```

### Bundle Profile Configurations

Define different bundle profiles for different use cases:

```json
{
  "organizations": {
    "company": {
      "bundle_profiles": {
        "quick-review": {
          "include_diff": false,
          "comment_limit": 5,
          "diff_context_lines": 1
        },
        "thorough-review": {
          "comment_limit": 50,
          "diff_context_lines": 10,
          "include_timestamps": true
        },
        "code-only": {
          "include_jira": false,
          "include_comments": false
        }
      }
    }
  }
}
```

## Configuration Validation

### Schema Validation

DevHub performs comprehensive validation of configuration files:

1. **JSON Syntax**: Valid JSON structure required
2. **Schema Compliance**: All fields must match expected types
3. **Reference Integrity**: `default_organization` must exist in `organizations`
4. **Value Ranges**: Numeric values must be within reasonable ranges

### Common Validation Errors

**Invalid default organization**:
```json
{
  "default_organization": "nonexistent",  // ERROR: Not in organizations
  "organizations": {
    "real-org": {}
  }
}
```

**Invalid timeout values**:
```json
{
  "jira": {
    "timeout_seconds": -5  // ERROR: Must be positive
  }
}
```

**Invalid permissions**:
```json
{
  "output": {
    "file_permissions": 999  // ERROR: Invalid octal permission
  }
}
```

## Debugging Configuration

### Configuration Inspection

Use built-in commands to inspect active configuration:

```bash
# Show effective configuration
devhub config show

# Show configuration sources
devhub config sources

# Validate configuration files
devhub config validate

# Show organization-specific settings
devhub config show --org client-alpha
```

### Configuration Debugging

Enable detailed configuration logging:

```bash
export DEVHUB_CONFIG_DEBUG=1
devhub bundle --jira-key PROJ-123
```

This shows:
- Configuration file search paths
- Which files were loaded
- How values were merged
- Final effective configuration

## Security Best Practices

### Credential Security

1. **Environment Variables Only**: Never store API tokens in files
2. **File Permissions**: Restrict config file access (`chmod 600 ~/.devhub/config.json`)
3. **Version Control**: Add `.devhub.json` to `.gitignore` for project configs with sensitive data
4. **Token Rotation**: Regularly rotate API tokens

### Safe Configuration Sharing

**Safe to share**:
```json
{
  "organizations": {
    "company": {
      "jira": {
        "base_url": "https://company.atlassian.net",
        "default_project_prefix": "PROJ"
      },
      "github": {
        "default_org": "company-org"
      }
    }
  }
}
```

**Never share**:
```json
{
  "jira": {
    "email": "user@company.com",     // Sensitive
    "api_token": "secret-token"      // Highly sensitive
  }
}
```

## Migration Guide

### Upgrading Configuration Format

When upgrading DevHub versions, configuration may need updates:

**Version 1.0 → 1.1** (hypothetical):
```bash
# Backup existing config
cp ~/.devhub/config.json ~/.devhub/config.json.backup

# Use migration tool
devhub config migrate --from 1.0 --to 1.1

# Verify migration
devhub config validate
```

### Legacy Configuration Support

DevHub maintains backward compatibility:

- **Version 1.0**: Current format (fully supported)
- **Environment-only**: Automatic migration to file-based config

## Functional Programming in Configuration

### Immutable Configuration Objects

All configuration is represented as **frozen dataclasses**:

```python
@dataclass(frozen=True, slots=True)
class JiraConfig:
    """Immutable Jira configuration."""
    base_url: str | None = None
    default_project_prefix: str | None = None
    timeout_seconds: int = 30
    # ... other fields
```

### Pure Configuration Functions

Configuration loading and merging uses pure functions:

```python
def merge_configs(base: DevHubConfig, override: DevHubConfig) -> DevHubConfig:
    """Pure function to merge two configurations."""
    # Returns new configuration object
    # No mutation of input parameters
```

### Result-Based Error Handling

Configuration operations return `Result` types:

```python
def load_config() -> Result[DevHubConfig, str]:
    """Load configuration with explicit error handling."""
    # Returns Success(config) or Failure(error_message)
```

## Best Practices Summary

1. **Hierarchical Organization**: Use global defaults, organization specifics, and project overrides
2. **Environment Variables**: Keep credentials in environment, structure in files
3. **Validation**: Always validate configuration before deployment
4. **Documentation**: Document organization-specific conventions
5. **Security**: Follow credential security best practices
6. **Immutability**: Treat configuration as immutable once loaded
7. **Type Safety**: Leverage DevHub's type-safe configuration system

## Troubleshooting

### Configuration Not Loading

1. Check file permissions: `ls -la ~/.devhub/config.json`
2. Validate JSON syntax: `python -m json.tool ~/.devhub/config.json`
3. Enable debug logging: `export DEVHUB_CONFIG_DEBUG=1`

### Organization Not Found

```bash
# List available organizations
devhub config organizations

# Set default organization
export DEVHUB_ORGANIZATION="correct-org-name"
```

### Permission Errors

```bash
# Fix file permissions
chmod 600 ~/.devhub/config.json
chmod 700 ~/.devhub/
```

---

This configuration system exemplifies **functional programming principles** while providing the flexibility needed for complex development environments. The immutable, type-safe approach ensures reliable, predictable configuration management across all DevHub operations.