# DevHub IDE Integrations

Complete step-by-step integration guides for VS Code and Cursor using the final DevHub SDK. All examples are tested and ready to use.

## Prerequisites

- **Python 3.13+**
- **DevHub installed**: `pip install devhub` or `uv add devhub`
- **GitHub CLI (`gh`)** authenticated in your repositories
- **Optional**: Jira credentials via environment variables
  - `JIRA_BASE_URL` (e.g., https://your-domain.atlassian.net)
  - `JIRA_EMAIL` (e.g., your.email@company.com)
  - `JIRA_API_TOKEN` (your Jira API token)

## Guide 1: VS Code Integration

This guide creates a VS Code task-based integration that uses the DevHub SDK to provide development context directly in your editor.

### Step 1: Create Python Bridge Script

Create `devhub_bridge.py` at your workspace root:

```python
#!/usr/bin/env python3
"""DevHub VS Code Bridge - Provides development context via the SDK."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from devhub.sdk import DevHubClient, ContextRequest
from returns.result import Success, Failure

async def get_context_async(args: argparse.Namespace) -> dict:
    """Get development context using DevHub SDK."""
    try:
        client = DevHubClient()
        await client.initialize()
        
        # Build context request from arguments
        request = ContextRequest(
            jira_key=args.jira_key,
            pr_number=args.pr_number,
            branch=args.branch,
            include_jira=not args.no_jira,
            include_pr=not args.no_pr,
            include_diff=not args.no_diff,
            include_comments=not args.no_comments,
            comment_limit=args.limit,
            metadata_only=args.metadata_only,
        )
        
        result = await client.get_bundle_context(request)
        
        match result:
            case Success(bundle):
                # Convert bundle to JSON-serializable format
                return {
                    "success": True,
                    "repository": {
                        "owner": bundle.repository.owner,
                        "name": bundle.repository.name,
                        "clone_url": bundle.repository.clone_url,
                        "default_branch": bundle.repository.default_branch
                    },
                    "branch": bundle.branch,
                    "jira_issue": {
                        "key": bundle.jira_issue.key,
                        "summary": bundle.jira_issue.summary,
                        "status": bundle.jira_issue.status,
                        "assignee": bundle.jira_issue.assignee,
                        "priority": bundle.jira_issue.priority,
                        "issue_type": bundle.jira_issue.issue_type,
                        "description": bundle.jira_issue.description,
                        "components": bundle.jira_issue.components,
                        "labels": bundle.jira_issue.labels
                    } if bundle.jira_issue else None,
                    "pr_data": bundle.pr_data,
                    "pr_diff": bundle.pr_diff if not args.metadata_only else None,
                    "comments": [
                        {
                            "author": comment.author,
                            "body": comment.body,
                            "file_path": comment.file_path,
                            "line_number": comment.line_number,
                            "created_at": comment.created_at
                        }
                        for comment in bundle.comments
                    ],
                    "stats": {
                        "comment_count": len(bundle.comments),
                        "has_diff": bool(bundle.pr_diff),
                        "files_changed": bundle.pr_data.get("changed_files", 0) if bundle.pr_data else 0
                    }
                }
            case Failure(error):
                return {
                    "success": False,
                    "error": str(error),
                    "suggestion": _get_error_suggestion(str(error))
                }
                
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {e}",
            "suggestion": "Check your DevHub installation and configuration"
        }

def _get_error_suggestion(error: str) -> str:
    """Provide helpful suggestions based on error type."""
    error_lower = error.lower()
    if "authentication" in error_lower:
        return "Run 'gh auth status' to check GitHub CLI authentication"
    elif "jira" in error_lower:
        return "Check your Jira environment variables (JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN)"
    elif "git" in error_lower:
        return "Ensure you're in a git repository directory"
    elif "network" in error_lower or "connection" in error_lower:
        return "Check your internet connection and API endpoints"
    else:
        return "Run 'devhub doctor' for comprehensive diagnostics"

def main() -> int:
    """Main entry point for the bridge script."""
    parser = argparse.ArgumentParser(description="DevHub VS Code Bridge")
    parser.add_argument("--jira-key", help="Jira issue key")
    parser.add_argument("--pr-number", type=int, help="PR number")
    parser.add_argument("--branch", help="Git branch name")
    parser.add_argument("--limit", type=int, default=20, help="Comment limit")
    parser.add_argument("--no-jira", action="store_true", help="Exclude Jira data")
    parser.add_argument("--no-pr", action="store_true", help="Exclude PR data")
    parser.add_argument("--no-diff", action="store_true", help="Exclude diff")
    parser.add_argument("--no-comments", action="store_true", help="Exclude comments")
    parser.add_argument("--metadata-only", action="store_true", help="Metadata only")
    
    args = parser.parse_args()
    
    # Run async function
    result = asyncio.run(get_context_async(args))
    
    # Output JSON result
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    return 0 if result.get("success", False) else 1

if __name__ == "__main__":
    sys.exit(main())
```

### Step 2: Create VS Code Tasks

Add to your `.vscode/tasks.json`:

```json
{
    "version": "2.0.0",
    "tasks": [
        {
            "label": "DevHub: Get Current Context",
            "type": "shell",
            "command": "python",
            "args": ["devhub_bridge.py", "--metadata-only"],
            "group": "build",
            "presentation": {
                "echo": true,
                "reveal": "always",
                "focus": false,
                "panel": "new"
            },
            "problemMatcher": []
        },
        {
            "label": "DevHub: Get Context with Diff",
            "type": "shell",
            "command": "python",
            "args": ["devhub_bridge.py"],
            "group": "build",
            "presentation": {
                "echo": true,
                "reveal": "always",
                "focus": false,
                "panel": "new"
            },
            "problemMatcher": []
        },
        {
            "label": "DevHub: Get Jira Context",
            "type": "shell",
            "command": "python",
            "args": [
                "devhub_bridge.py",
                "--jira-key",
                "${input:jiraKey}",
                "--metadata-only"
            ],
            "group": "build",
            "presentation": {
                "echo": true,
                "reveal": "always",
                "focus": false,
                "panel": "new"
            },
            "problemMatcher": []
        }
    ],
    "inputs": [
        {
            "id": "jiraKey",
            "description": "Enter Jira issue key (e.g., PROJ-123)",
            "default": "PROJ-123",
            "type": "promptString"
        }
    ]
}
```

### Step 3: Add Keyboard Shortcuts

Add to your `.vscode/keybindings.json`:

```json
[
    {
        "key": "ctrl+shift+d",
        "command": "workbench.action.tasks.runTask",
        "args": "DevHub: Get Current Context"
    },
    {
        "key": "ctrl+shift+alt+d",
        "command": "workbench.action.tasks.runTask",
        "args": "DevHub: Get Context with Diff"
    }
]
```

### Step 4: Usage in VS Code

1. **Quick Context**: Press `Ctrl+Shift+D` to get current context
2. **Full Context**: Press `Ctrl+Shift+Alt+D` to include diff
3. **Command Palette**: Search for "Tasks: Run Task" and select DevHub tasks
4. **Terminal**: Run `python devhub_bridge.py --help` for all options

## Guide 2: Cursor Integration

Cursor provides excellent Python integration, making DevHub SDK usage straightforward.

### Step 1: Create Cursor-Optimized Script

Create `cursor_devhub.py` in your workspace:

```python
#!/usr/bin/env python3
"""DevHub Cursor Integration - Optimized for Cursor's AI features."""

import asyncio
import json
import sys
from typing import Any, Dict

from devhub.sdk import DevHubClient, ContextRequest
from returns.result import Success, Failure

class CursorDevHubBridge:
    """DevHub bridge optimized for Cursor AI integration."""
    
    def __init__(self):
        self.client = DevHubClient()
        self._initialized = False
    
    async def initialize(self) -> bool:
        """Initialize the DevHub client."""
        if self._initialized:
            return True
            
        result = await self.client.initialize()
        self._initialized = isinstance(result, Success)
        return self._initialized
    
    async def get_current_context(self, include_diff: bool = False) -> Dict[str, Any]:
        """Get context for current branch - optimized for AI consumption."""
        if not await self.initialize():
            return {"error": "Failed to initialize DevHub client"}
        
        request = ContextRequest(
            include_diff=include_diff,
            include_comments=True,
            comment_limit=25,
            metadata_only=not include_diff
        )
        
        result = await self.client.get_bundle_context(request)
        
        match result:
            case Success(bundle):
                return self._format_for_cursor(bundle, include_diff)
            case Failure(error):
                return {"error": str(error)}
    
    async def get_jira_context(self, jira_key: str) -> Dict[str, Any]:
        """Get specific Jira issue context."""
        if not await self.initialize():
            return {"error": "Failed to initialize DevHub client"}
        
        request = ContextRequest(
            jira_key=jira_key,
            include_jira=True,
            include_pr=True,
            include_diff=False,
            include_comments=True,
            comment_limit=20,
            metadata_only=True
        )
        
        result = await self.client.get_bundle_context(request)
        
        match result:
            case Success(bundle):
                return self._format_for_cursor(bundle, False)
            case Failure(error):
                return {"error": str(error)}
    
    async def get_pr_context(self, pr_number: int, include_diff: bool = True) -> Dict[str, Any]:
        """Get specific PR context with optional diff."""
        if not await self.initialize():
            return {"error": "Failed to initialize DevHub client"}
        
        request = ContextRequest(
            pr_number=pr_number,
            include_pr=True,
            include_diff=include_diff,
            include_comments=True,
            comment_limit=30,
            metadata_only=False
        )
        
        result = await self.client.get_bundle_context(request)
        
        match result:
            case Success(bundle):
                return self._format_for_cursor(bundle, include_diff)
            case Failure(error):
                return {"error": str(error)}
    
    def _format_for_cursor(self, bundle, include_diff: bool) -> Dict[str, Any]:
        """Format bundle data for optimal Cursor AI consumption."""
        context = {
            "repository": {
                "name": f"{bundle.repository.owner}/{bundle.repository.name}",
                "branch": bundle.branch,
                "clone_url": bundle.repository.clone_url
            },
            "development_context": {}
        }
        
        # Add Jira context if available
        if bundle.jira_issue:
            context["development_context"]["jira"] = {
                "key": bundle.jira_issue.key,
                "title": bundle.jira_issue.summary,
                "status": bundle.jira_issue.status,
                "assignee": bundle.jira_issue.assignee,
                "priority": bundle.jira_issue.priority,
                "type": bundle.jira_issue.issue_type,
                "description": bundle.jira_issue.description,
                "components": bundle.jira_issue.components,
                "labels": bundle.jira_issue.labels
            }
        
        # Add PR context if available
        if bundle.pr_data:
            pr = bundle.pr_data
            context["development_context"]["pull_request"] = {
                "number": pr.get("number"),
                "title": pr.get("title"),
                "state": pr.get("state"),
                "author": pr.get("user", {}).get("login"),
                "mergeable": pr.get("mergeable"),
                "mergeable_state": pr.get("mergeable_state"),
                "files_changed": pr.get("changed_files", 0),
                "additions": pr.get("additions", 0),
                "deletions": pr.get("deletions", 0),
                "url": pr.get("html_url")
            }
        
        # Add diff if requested
        if include_diff and bundle.pr_diff:
            context["development_context"]["diff"] = {
                "content": bundle.pr_diff,
                "size_chars": len(bundle.pr_diff)
            }
        
        # Add unresolved comments
        if bundle.comments:
            context["development_context"]["unresolved_comments"] = [
                {
                    "author": comment.author,
                    "content": comment.body,
                    "file": comment.file_path,
                    "line": comment.line_number,
                    "created": comment.created_at
                }
                for comment in bundle.comments
            ]
        
        # Add AI-friendly summary
        context["ai_summary"] = self._generate_ai_summary(bundle)
        
        return context
    
    def _generate_ai_summary(self, bundle) -> Dict[str, Any]:
        """Generate a summary optimized for AI understanding."""
        summary = {
            "context_type": "development_work",
            "has_jira_issue": bundle.jira_issue is not None,
            "has_pull_request": bundle.pr_data is not None,
            "has_code_changes": bundle.pr_diff is not None,
            "unresolved_comment_count": len(bundle.comments),
            "attention_needed": len(bundle.comments) > 0
        }
        
        if bundle.jira_issue:
            summary["jira_summary"] = f"{bundle.jira_issue.key}: {bundle.jira_issue.summary}"
            summary["work_status"] = bundle.jira_issue.status
        
        if bundle.pr_data:
            summary["pr_summary"] = f"PR #{bundle.pr_data.get('number')}: {bundle.pr_data.get('title')}"
            summary["pr_state"] = bundle.pr_data.get("state")
        
        if bundle.comments:
            summary["review_focus_areas"] = list({
                comment.file_path for comment in bundle.comments[:5]
            })
        
        return summary

# CLI interface
async def main():
    bridge = CursorDevHubBridge()
    
    if len(sys.argv) < 2:
        print("Usage: python cursor_devhub.py <command> [args]")
        print("Commands: current, jira <key>, pr <number> [--diff]")
        return 1
    
    command = sys.argv[1].lower()
    
    try:
        if command == "current":
            include_diff = "--diff" in sys.argv
            result = await bridge.get_current_context(include_diff)
        elif command == "jira" and len(sys.argv) > 2:
            jira_key = sys.argv[2]
            result = await bridge.get_jira_context(jira_key)
        elif command == "pr" and len(sys.argv) > 2:
            pr_number = int(sys.argv[2])
            include_diff = "--diff" in sys.argv
            result = await bridge.get_pr_context(pr_number, include_diff)
        else:
            print("Invalid command or missing arguments")
            return 1
        
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
        
    except Exception as e:
        print(json.dumps({"error": str(e)}, indent=2))
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

### Step 2: Create Cursor Workflow Documentation

Create `.cursor/devhub_workflow.md` to document AI-friendly workflows:

```markdown
# DevHub Integration Workflows for Cursor

## Quick Commands

### Get Current Development Context
```bash
python cursor_devhub.py current
```

### Get Current Context with Code Diff
```bash
python cursor_devhub.py current --diff
```

### Get Specific Jira Issue Context
```bash
python cursor_devhub.py jira PROJ-123
```

### Get Specific PR Context
```bash
python cursor_devhub.py pr 456 --diff
```

## AI Integration Examples

Ask Cursor AI to:
- "Run the DevHub current context command and analyze what I should focus on"
- "Get the context for PROJ-123 and suggest an implementation approach"
- "Show me PR 456 with the diff and review the changes"
- "Based on the DevHub context, what are the priority items to address?"

## Workflow Tips

1. **Start with context**: Always get the development context before asking for code assistance
2. **Reference specific data**: Use "Based on the DevHub context..." to ground AI responses
3. **Combine with analysis**: Ask AI to analyze the context and provide actionable insights
4. **Use for code review**: Get PR context with diff and ask for review feedback
```

### Step 3: Usage in Cursor

1. **Terminal Integration**: Open terminal and run commands directly
2. **AI Chat Integration**: Ask Cursor to run DevHub commands and analyze results
3. **Workflow Integration**: Use the documented workflows for consistent AI assistance

Example AI conversation:
```
You: "Run python cursor_devhub.py current and tell me what I should work on"

Cursor: [Runs command and analyzes output]
"Based on the DevHub context, you're working on branch feature/user-auth in the myapp/backend repository. There's an open Jira issue AUTH-456 about implementing OAuth integration, and you have 3 unresolved PR comments that need attention in the authentication middleware files."
```

## Testing Your Integration

### Test VS Code Integration

1. Open VS Code in a git repository
2. Ensure `devhub_bridge.py` is in the workspace root
3. Press `Ctrl+Shift+D` to test the quick context task
4. Check the terminal output for JSON response

### Test Cursor Integration

1. Open terminal in your project directory
2. Run: `python cursor_devhub.py current`
3. Verify structured JSON output is returned
4. Test AI integration: Ask Cursor to run the command and analyze results

### Troubleshooting

**Common Issues:**

1. **Python not found**: Ensure Python 3.13+ is in your PATH
2. **DevHub not installed**: Run `pip install devhub` or `uv add devhub`
3. **GitHub authentication**: Run `gh auth status` to verify
4. **Jira credentials**: Set environment variables or run `devhub doctor`
5. **Repository context**: Ensure you're in a git repository directory

**Debug Commands:**

```bash
# Test DevHub installation
devhub --version
devhub doctor

# Test bridge scripts
python devhub_bridge.py --help
python cursor_devhub.py current

# Verify dependencies
python -c "from devhub.sdk import DevHubClient; print('SDK available')"
```

Both integrations provide seamless access to DevHub's development context directly within your IDE, enabling AI-assisted development workflows with complete project awareness.
