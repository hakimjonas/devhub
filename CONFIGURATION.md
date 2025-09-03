# DevHub Configuration Guide

> **Complete guide to DevHub's hierarchical configuration system**

DevHub's configuration system is designed around **immutable data structures** and **functional principles**, providing flexible, type-safe configuration management for multi-organization environments.

## Configuration Architecture

### Search Order and Loading

DevHub looks for a JSON config file in this order and loads the first one that exists:

1. Explicit path via environment: `DEVHUB_CONFIG=/absolute/path/to/config.json`
2. Project-local: `./.devhub.json`
3. XDG user config: `$XDG_CONFIG_HOME/devhub/config.json` (default: `~/.config/devhub/config.json`)
4. XDG system dirs: each `$XDG_CONFIG_DIRS/devhub/config.json` (default: `/etc/xdg/devhub/config.json`)

Note: Only the first existing file is loaded; there is no automatic merging across multiple files. Environment variables can still override values after loading.

### Configuration Override Strategy

Final configuration is produced as:

```
First-found JSON file → Environment variable overrides
```

Each level can provide partial configuration; missing values fall back to built-in defaults.

## Configuration Schema

### Root Configuration Structure

```json
{
  "config_version": "1.0",
  "default_organization": "organization-name",
  "organizations": {
    "org-name": "Organization configuration object"
  },
  "jira": "Global Jira settings object",
  "github": "Global GitHub settings object",
  "output": "Global output settings object"
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
  "jira": {
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

Use environment variables for credentials (never store tokens in files):

```bash
# Jira Authentication
export JIRA_EMAIL="your-email@company.com"
export JIRA_API_TOKEN="your-api-token"
```

### Path and Organization Overrides

```bash
# Explicit config file path (highest precedence)
export DEVHUB_CONFIG="/absolute/path/to/config.json"

# Override default organization selection
export DEVHUB_ORGANIZATION="client-alpha"
```

### Dynamic Configuration Overrides

```bash
# Override timeouts for current session
export JIRA_TIMEOUT_SECONDS="90"
export GITHUB_TIMEOUT_SECONDS="60"

# Override output directory for bundles
export BUNDLE_OUTPUT_DIR="/tmp/reviews"
```

Supported environment variables (summary):
- DEVHUB_CONFIG: absolute path to config JSON
- DEVHUB_ORGANIZATION: sets default_organization at runtime
- JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_DEFAULT_PROJECT, JIRA_TIMEOUT_SECONDS
- GITHUB_DEFAULT_ORG, GITHUB_TIMEOUT_SECONDS
- BUNDLE_OUTPUT_DIR

## Advanced Configuration Patterns

### Configuration Placement

Prefer XDG locations for user/system config:
- User: `$XDG_CONFIG_HOME/devhub/config.json` (defaults to `~/.config/devhub/config.json`)
- System: each `$XDG_CONFIG_DIRS/devhub/config.json` (defaults to `/etc/xdg/devhub/config.json`)

Project-specific overrides can live at `./.devhub.json` and will win over user/system files.

### Bundle Profile Configurations

Define different bundle profiles for different use cases (consumer logic can choose which to apply):

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

DevHub validates:
1. JSON syntax
2. Schema basics (object shape)
3. Reference integrity: `default_organization` must exist in `organizations` if provided

## Debugging Configuration

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

Enable detailed configuration logging:

```bash
export DEVHUB_CONFIG_DEBUG=1
devhub bundle --jira-key PROJ-123
```

This shows search paths, which file was loaded, environment overlays, and the final effective configuration.

## Security Best Practices

1. Environment variables only for secrets
2. Restrict config file permissions (`chmod 600 ~/.config/devhub/config.json`)
3. Add `.devhub.json` to `.gitignore` in repos
4. Rotate API tokens regularly

---

This configuration system follows **functional programming principles** with **immutable dataclasses** and explicit `Result`-based error handling for reliable, predictable configuration management.
