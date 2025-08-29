# DevHub IDE Integration Patterns

> **Complete guide for integrating DevHub with popular IDEs and code agents**

This document provides practical integration patterns for using DevHub with various IDEs, code agents, and development tools. All examples maintain DevHub's functional programming principles and provide type-safe, reliable integrations.

## Overview

DevHub can be integrated with IDEs and code agents in several ways:

1. **CLI Integration** - Direct command line usage with JSON output
2. **MCP Integration** - Model Context Protocol for AI agents
3. **Programmatic SDK** - Python API for custom integrations
4. **Extension Patterns** - IDE-specific extension examples

## VS Code Integration

### Method 1: VS Code Extension with CLI

Create a VS Code extension that calls DevHub CLI commands:

```typescript
// src/extension.ts
import * as vscode from 'vscode';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

interface DevHubBundle {
    metadata: {
        repository?: {
            owner: string;
            name: string;
        };
        branch?: string;
        jira_key?: string;
        pr_number?: number;
    };
    jira?: any;
    pull_request?: any;
    diff?: string;
    comments?: any[];
}

class DevHubProvider {
    constructor(private workspaceRoot: string) {}

    async getBundleContext(options?: {
        jiraKey?: string;
        prNumber?: number;
        includeComments?: boolean;
        limit?: number;
    }): Promise<DevHubBundle> {
        const args = ['bundle', '--format', 'json', '--stdout'];
        
        if (options?.jiraKey) {
            args.push('--jira-key', options.jiraKey);
        }
        if (options?.prNumber) {
            args.push('--pr', options.prNumber.toString());
        }
        if (options?.includeComments === false) {
            args.push('--no-comments');
        }
        if (options?.limit) {
            args.push('--limit', options.limit.toString());
        }

        const command = `uv run devhub ${args.join(' ')}`;
        
        try {
            const { stdout } = await execAsync(command, { 
                cwd: this.workspaceRoot 
            });
            return JSON.parse(stdout) as DevHubBundle;
        } catch (error) {
            throw new Error(`DevHub command failed: ${error}`);
        }
    }

    async getCurrentBranchContext(): Promise<DevHubBundle> {
        return this.getBundleContext();
    }

    async getPRDetails(prNumber: number): Promise<any> {
        const bundle = await this.getBundleContext({ 
            prNumber, 
            includeComments: false 
        });
        return bundle.pull_request;
    }
}

// Extension activation
export function activate(context: vscode.ExtensionContext) {
    const workspaceRoot = vscode.workspace.rootPath;
    if (!workspaceRoot) {
        return;
    }

    const devhub = new DevHubProvider(workspaceRoot);

    // Command: Get current branch context
    const getCurrentContext = vscode.commands.registerCommand(
        'devhub.getCurrentContext', 
        async () => {
            try {
                const context = await devhub.getCurrentBranchContext();
                
                // Create a new document with the context
                const doc = await vscode.workspace.openTextDocument({
                    content: JSON.stringify(context, null, 2),
                    language: 'json'
                });
                await vscode.window.showTextDocument(doc);
                
                vscode.window.showInformationMessage(
                    `DevHub context loaded for ${context.metadata.branch}`
                );
            } catch (error) {
                vscode.window.showErrorMessage(`DevHub error: ${error}`);
            }
        }
    );

    // Command: Get bundle for specific Jira key
    const getBundleForJira = vscode.commands.registerCommand(
        'devhub.getBundleForJira',
        async () => {
            const jiraKey = await vscode.window.showInputBox({
                prompt: 'Enter Jira issue key (e.g., PROJ-123)',
                validateInput: (value) => {
                    if (!value || !/^[A-Z][A-Z0-9]+-\d+$/.test(value)) {
                        return 'Please enter a valid Jira key (e.g., PROJ-123)';
                    }
                    return null;
                }
            });

            if (jiraKey) {
                try {
                    const bundle = await devhub.getBundleContext({ jiraKey });
                    
                    // Show summary in output channel
                    const outputChannel = vscode.window.createOutputChannel('DevHub');
                    outputChannel.appendLine(`Bundle for ${jiraKey}:`);
                    outputChannel.appendLine(`Branch: ${bundle.metadata.branch}`);
                    outputChannel.appendLine(`PR: #${bundle.metadata.pr_number || 'N/A'}`);
                    if (bundle.jira) {
                        outputChannel.appendLine(`Jira: ${bundle.jira.summary}`);
                    }
                    outputChannel.show();
                    
                } catch (error) {
                    vscode.window.showErrorMessage(`DevHub error: ${error}`);
                }
            }
        }
    );

    context.subscriptions.push(getCurrentContext, getBundleForJira);
}
```

### Method 2: VS Code with MCP Integration

For AI-powered code assistance with DevHub context:

```typescript
// src/mcpIntegration.ts
import * as vscode from 'vscode';
import { spawn } from 'child_process';

class DevHubMCPClient {
    private mcpProcess: any;

    async startMCPServer(): Promise<void> {
        const workspaceRoot = vscode.workspace.rootPath;
        if (!workspaceRoot) {
            throw new Error('No workspace root found');
        }

        this.mcpProcess = spawn('uv', ['run', 'devhub-mcp'], {
            cwd: workspaceRoot,
            stdio: ['pipe', 'pipe', 'pipe']
        });

        // Initialize MCP connection
        await this.sendMCPRequest({
            jsonrpc: '2.0',
            method: 'initialize',
            params: {},
            id: 1
        });
    }

    async sendMCPRequest(request: any): Promise<any> {
        return new Promise((resolve, reject) => {
            const requestStr = JSON.stringify(request) + '\n';
            this.mcpProcess.stdin.write(requestStr);

            this.mcpProcess.stdout.once('data', (data: Buffer) => {
                try {
                    const response = JSON.parse(data.toString());
                    if (response.error) {
                        reject(new Error(response.error.message));
                    } else {
                        resolve(response.result);
                    }
                } catch (error) {
                    reject(error);
                }
            });
        });
    }

    async getBundleContext(): Promise<any> {
        return this.sendMCPRequest({
            jsonrpc: '2.0',
            method: 'tools/call',
            params: {
                name: 'get-current-branch-context',
                arguments: {
                    include_diff: true,
                    include_comments: true,
                    comment_limit: 20
                }
            },
            id: Date.now()
        });
    }

    dispose(): void {
        if (this.mcpProcess) {
            this.mcpProcess.kill();
        }
    }
}
```

## Cursor IDE Integration

### Python Integration for Cursor

Create a Python script that Cursor can use to get DevHub context:

```python
# cursor_devhub.py
"""DevHub integration for Cursor IDE."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


class DevHubCursorIntegration:
    """DevHub integration for Cursor IDE code agents."""

    def __init__(self, workspace_path: Optional[str] = None):
        """Initialize DevHub integration."""
        self.workspace_path = Path(workspace_path) if workspace_path else Path.cwd()

    def get_bundle_context(
        self,
        jira_key: Optional[str] = None,
        pr_number: Optional[int] = None,
        include_diff: bool = True,
        include_comments: bool = True,
        comment_limit: int = 20,
    ) -> Dict[str, Any]:
        """Get comprehensive bundle context for current work."""
        cmd = [
            "uv", "run", "devhub", "bundle",
            "--format", "json",
            "--stdout",
            "--limit", str(comment_limit)
        ]
        
        if jira_key:
            cmd.extend(["--jira-key", jira_key])
        if pr_number:
            cmd.extend(["--pr", str(pr_number)])
        if not include_diff:
            cmd.append("--no-diff")
        if not include_comments:
            cmd.append("--no-comments")

        try:
            result = subprocess.run(
                cmd,
                cwd=self.workspace_path,
                capture_output=True,
                text=True,
                check=True
            )
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"DevHub command failed: {e.stderr}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse DevHub output: {e}")

    def get_current_branch_context(self) -> Dict[str, Any]:
        """Get context for current branch with auto-detection."""
        return self.get_bundle_context()

    def get_pr_context(
        self, 
        pr_number: int, 
        include_diff: bool = True
    ) -> Dict[str, Any]:
        """Get specific PR context."""
        return self.get_bundle_context(
            pr_number=pr_number,
            include_diff=include_diff,
            include_comments=True
        )

    def get_jira_context(self, jira_key: str) -> Dict[str, Any]:
        """Get specific Jira issue context."""
        return self.get_bundle_context(
            jira_key=jira_key,
            include_diff=False,
            include_comments=False
        )

    def format_context_for_agent(self, context: Dict[str, Any]) -> str:
        """Format context in a way that's useful for code agents."""
        lines = []
        
        # Repository info
        if repo := context.get("metadata", {}).get("repository"):
            lines.append(f"Repository: {repo['owner']}/{repo['name']}")
        
        # Branch info
        if branch := context.get("metadata", {}).get("branch"):
            lines.append(f"Branch: {branch}")
        
        # Jira issue
        if jira := context.get("jira"):
            lines.append(f"\n## Jira Issue: {jira['key']}")
            lines.append(f"Summary: {jira['summary']}")
            if jira.get("description"):
                lines.append(f"Description: {jira['description']}")
        
        # PR info
        if pr := context.get("pull_request"):
            lines.append(f"\n## Pull Request: #{pr['number']}")
            lines.append(f"Title: {pr['title']}")
            if pr.get("body"):
                lines.append(f"Description: {pr['body']}")
        
        # Code diff (truncated)
        if diff := context.get("diff"):
            lines.append("\n## Code Changes:")
            diff_lines = diff.split('\n')
            if len(diff_lines) > 50:
                lines.extend(diff_lines[:25])
                lines.append("... (truncated for brevity) ...")
                lines.extend(diff_lines[-25:])
            else:
                lines.append(diff)
        
        # Comments summary
        if comments := context.get("comments"):
            lines.append(f"\n## Review Comments ({len(comments)} unresolved):")
            for comment in comments[:5]:  # Show first 5 comments
                lines.append(f"- {comment['author']}: {comment['body'][:100]}...")
            if len(comments) > 5:
                lines.append(f"... and {len(comments) - 5} more comments")
        
        return "\n".join(lines)


# Example usage for Cursor
def main():
    """Main function for command-line usage."""
    if len(sys.argv) < 2:
        print("Usage: python cursor_devhub.py <command> [args...]")
        print("Commands:")
        print("  current-context - Get current branch context")
        print("  pr-context <number> - Get PR context")
        print("  jira-context <key> - Get Jira context")
        return

    devhub = DevHubCursorIntegration()
    command = sys.argv[1]

    try:
        if command == "current-context":
            context = devhub.get_current_branch_context()
            print(devhub.format_context_for_agent(context))
        elif command == "pr-context" and len(sys.argv) > 2:
            pr_number = int(sys.argv[2])
            context = devhub.get_pr_context(pr_number)
            print(devhub.format_context_for_agent(context))
        elif command == "jira-context" and len(sys.argv) > 2:
            jira_key = sys.argv[2]
            context = devhub.get_jira_context(jira_key)
            print(devhub.format_context_for_agent(context))
        else:
            print(f"Unknown command or missing arguments: {command}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

### Cursor Configuration

Add to your Cursor settings:

```json
{
  "cursor.general.enableContextProvider": true,
  "cursor.contextProviders": [
    {
      "name": "devhub-context",
      "command": "python",
      "args": ["cursor_devhub.py", "current-context"],
      "description": "Get DevHub context for current work"
    }
  ]
}
```

## Continue.dev Integration

### Continue.dev Context Provider

```typescript
// devhub-context-provider.ts
import { ContextProvider, ContextProviderWithParams } from "@continuedev/core";
import { exec } from "child_process";
import { promisify } from "util";

const execAsync = promisify(exec);

interface DevHubContextParams {
  jiraKey?: string;
  prNumber?: number;
  includeComments?: boolean;
}

export class DevHubContextProvider implements ContextProviderWithParams {
  static description = "Get development context from DevHub";
  
  async getContextItems(
    query: string,
    extras: DevHubContextParams
  ): Promise<any[]> {
    try {
      const args = ["bundle", "--format", "json", "--stdout"];
      
      if (extras.jiraKey) {
        args.push("--jira-key", extras.jiraKey);
      }
      if (extras.prNumber) {
        args.push("--pr", extras.prNumber.toString());
      }
      if (extras.includeComments === false) {
        args.push("--no-comments");
      }

      const command = `uv run devhub ${args.join(" ")}`;
      const { stdout } = await execAsync(command);
      const context = JSON.parse(stdout);

      const items = [];

      // Add Jira context
      if (context.jira) {
        items.push({
          name: `Jira: ${context.jira.key}`,
          description: context.jira.summary,
          content: this.formatJiraContext(context.jira),
        });
      }

      // Add PR context
      if (context.pull_request) {
        items.push({
          name: `PR #${context.pull_request.number}`,
          description: context.pull_request.title,
          content: this.formatPRContext(context.pull_request),
        });
      }

      // Add diff context
      if (context.diff) {
        items.push({
          name: "Code Changes",
          description: "Current diff",
          content: `\`\`\`diff\n${context.diff}\n\`\`\``,
        });
      }

      // Add comments context
      if (context.comments?.length > 0) {
        items.push({
          name: "Review Comments",
          description: `${context.comments.length} unresolved comments`,
          content: this.formatCommentsContext(context.comments),
        });
      }

      return items;

    } catch (error) {
      return [{
        name: "DevHub Error",
        description: "Failed to get context",
        content: `Error: ${error}`,
      }];
    }
  }

  private formatJiraContext(jira: any): string {
    let content = `# ${jira.key}: ${jira.summary}\n\n`;
    if (jira.description) {
      content += `## Description\n${jira.description}\n\n`;
    }
    return content;
  }

  private formatPRContext(pr: any): string {
    let content = `# PR #${pr.number}: ${pr.title}\n\n`;
    if (pr.body) {
      content += `## Description\n${pr.body}\n\n`;
    }
    content += `**Author:** ${pr.user?.login}\n`;
    content += `**Created:** ${pr.created_at}\n`;
    return content;
  }

  private formatCommentsContext(comments: any[]): string {
    let content = "# Review Comments\n\n";
    comments.forEach((comment, index) => {
      content += `## Comment ${index + 1}\n`;
      content += `**Author:** ${comment.author}\n`;
      content += `**File:** ${comment.path || 'General'}\n`;
      content += `**Comment:** ${comment.body}\n\n`;
      if (comment.diff_hunk) {
        content += `**Context:**\n\`\`\`diff\n${comment.diff_hunk}\n\`\`\`\n\n`;
      }
    });
    return content;
  }
}
```

### Continue.dev Configuration

Add to your `.continue/config.json`:

```json
{
  "contextProviders": [
    {
      "name": "devhub",
      "params": {
        "includeComments": true
      }
    }
  ]
}
```

## GitHub Copilot Integration

### Copilot Context Script

```bash
#!/bin/bash
# .github/copilot/devhub-context.sh

# Get DevHub context for GitHub Copilot
cd "$(dirname "$0")/../.."

# Get current context
CONTEXT=$(uv run devhub bundle --format compact --stdout --metadata-only 2>/dev/null)

if [ $? -eq 0 ] && [ -n "$CONTEXT" ]; then
    echo "DevHub Context:"
    echo "$CONTEXT" | jq -r '
        "Repository: " + (.metadata.repository.owner // "unknown") + "/" + (.metadata.repository.name // "unknown") +
        " | Branch: " + (.metadata.branch // "unknown") +
        (if .metadata.jira_key then " | Jira: " + .metadata.jira_key else "" end) +
        (if .metadata.pr_number then " | PR: #" + (.metadata.pr_number | tostring) else "" end)
    '
else
    echo "DevHub context not available"
fi
```

### Copilot Integration with Comments

```javascript
// copilot-devhub-integration.js
const { execSync } = require('child_process');

/**
 * Get DevHub context for GitHub Copilot suggestions
 */
function getDevHubContext() {
    try {
        const result = execSync('uv run devhub bundle --format compact --stdout', {
            encoding: 'utf8',
            timeout: 10000
        });
        
        const context = JSON.parse(result);
        
        // Format for Copilot comment
        let contextString = '';
        
        if (context.metadata?.repository) {
            contextString += `Repository: ${context.metadata.repository.owner}/${context.metadata.repository.name}\n`;
        }
        
        if (context.metadata?.branch) {
            contextString += `Branch: ${context.metadata.branch}\n`;
        }
        
        if (context.jira?.key) {
            contextString += `Jira: ${context.jira.key} - ${context.jira.summary}\n`;
        }
        
        if (context.pull_request?.number) {
            contextString += `PR: #${context.pull_request.number} - ${context.pull_request.title}\n`;
        }
        
        return contextString;
        
    } catch (error) {
        return `DevHub context unavailable: ${error.message}`;
    }
}

// Example usage in code comments for Copilot
/*
DevHub Context:
${getDevHubContext()}

Based on this context, help me implement the following functionality:
*/
```

## Integration Best Practices

### 1. Error Handling

Always handle DevHub command failures gracefully:

```typescript
async function safeDevHubCall(command: string[]): Promise<any> {
    try {
        const { stdout } = await execAsync(`uv run devhub ${command.join(' ')}`);
        return JSON.parse(stdout);
    } catch (error) {
        console.warn(`DevHub command failed: ${error}`);
        return null;
    }
}
```

### 2. Performance Optimization

Cache DevHub results to avoid repeated API calls:

```python
import time
from functools import lru_cache
from typing import Dict, Any, Optional

class DevHubCache:
    def __init__(self, cache_ttl: int = 300):  # 5 minutes
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, tuple[float, Any]] = {}
    
    def get_cached_bundle(
        self, 
        cache_key: Optional[str] = None,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Get cached bundle or None if expired/missing."""
        key = cache_key or self._make_cache_key(**kwargs)
        
        if key in self._cache:
            timestamp, data = self._cache[key]
            if time.time() - timestamp < self.cache_ttl:
                return data
            else:
                del self._cache[key]
        
        return None
    
    def cache_bundle(
        self, 
        data: Dict[str, Any],
        cache_key: Optional[str] = None,
        **kwargs
    ) -> None:
        """Cache bundle data."""
        key = cache_key or self._make_cache_key(**kwargs)
        self._cache[key] = (time.time(), data)
    
    def _make_cache_key(self, **kwargs) -> str:
        """Generate cache key from arguments."""
        return f"bundle_{hash(frozenset(kwargs.items()))}"
```

### 3. Type Safety

Use TypeScript interfaces for better IDE support:

```typescript
interface DevHubBundle {
    metadata: {
        repository?: {
            owner: string;
            name: string;
        };
        branch?: string;
        jira_key?: string;
        pr_number?: number;
        generated_at: string;
    };
    jira?: {
        key: string;
        summary?: string;
        description?: string;
        raw_data: any;
    };
    pull_request?: {
        number: number;
        title: string;
        body?: string;
        user?: {
            login: string;
        };
        created_at: string;
    };
    diff?: string;
    comments?: Array<{
        id: string;
        body: string;
        path?: string;
        author?: string;
        created_at?: string;
        diff_hunk?: string;
        resolved: boolean;
    }>;
}
```

## Testing Integrations

### Unit Tests for VS Code Extension

```typescript
// test/extension.test.ts
import * as assert from 'assert';
import { DevHubProvider } from '../src/extension';

suite('DevHub Extension Tests', () => {
    const mockWorkspace = '/path/to/test/workspace';
    let devhub: DevHubProvider;

    setup(() => {
        devhub = new DevHubProvider(mockWorkspace);
    });

    test('should get bundle context', async () => {
        const context = await devhub.getBundleContext({
            jiraKey: 'TEST-123'
        });
        
        assert.ok(context);
        assert.strictEqual(context.metadata?.jira_key, 'TEST-123');
    });

    test('should handle errors gracefully', async () => {
        try {
            await devhub.getBundleContext({ jiraKey: 'INVALID' });
            assert.fail('Should have thrown an error');
        } catch (error) {
            assert.ok(error instanceof Error);
        }
    });
});
```

---

These integration patterns demonstrate how DevHub's functional programming architecture and type-safe design enable reliable, maintainable IDE integrations across different platforms and use cases.