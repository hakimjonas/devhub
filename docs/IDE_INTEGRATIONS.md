# DevHub IDE Integrations

Two proven, step-by-step integration paths using the final SDK. Copy, paste, and adapt.

Requirements
- Python 3.13+
- uv (or your Python runner)
- GitHub CLI (gh) authenticated in your repos
- Optional: JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN

Guide 1 — VS Code (TypeScript extension) via Python SDK bridge
Recommended: call a tiny Python script that uses the DevHubAsyncClient and prints JSON. This avoids relying on CLI flags and keeps logic in one place.

Step 1: Add a Python bridge script
Create devhub_ide_bridge.py at your workspace root:

```python
# devhub_ide_bridge.py
import argparse
import asyncio
import json
from devhub.sdk import DevHubAsyncClient, ContextRequest
from returns.result import Success, Failure

async def run_async(args: argparse.Namespace) -> int:
    req = ContextRequest(
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
    async with DevHubAsyncClient() as client:
        result = await client.get_bundle_context(req)
    match result:
        case Success(bundle):
            print(json.dumps(bundle.to_dict(include_content=not args.metadata_only), ensure_ascii=False))
            return 0
        case Failure(error):
            print(json.dumps({"error": error}, ensure_ascii=False))
            return 1
    # Fallback (should not be reached)
    return 1

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--jira-key")
    p.add_argument("--pr-number", type=int)
    p.add_argument("--branch")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--no-jira", action="store_true")
    p.add_argument("--no-pr", action="store_true")
    p.add_argument("--no-diff", action="store_true")
    p.add_argument("--no-comments", action="store_true")
    p.add_argument("--metadata-only", action="store_true")
    args = p.parse_args()
    return asyncio.run(run_async(args))

if __name__ == "__main__":
    raise SystemExit(main())
```

Step 2: Call the bridge from your extension

```ts
// src/extension.ts
import * as vscode from 'vscode';
import { execFile } from 'child_process';
import { promisify } from 'util';

const execFileAsync = promisify(execFile);

// Strongly-typed bundle shape returned by the Python bridge
interface DevHubBundle {
  metadata: {
    repository?: { owner: string; name: string } | null;
    branch?: string | null;
    generated_at: string;
    // Additional metadata keys may be present
    [k: string]: unknown;
  };
  jira?: {
    key: string;
    summary?: string | null;
    description?: string | null;
    raw_data: unknown;
  };
  pull_request?: {
    number: number;
    title: string;
    body?: string | null;
    [k: string]: unknown;
  };
  diff?: string;
  comments?: Array<{
    id: string;
    body: string;
    path?: string | null;
    author?: string | null;
    created_at?: string | null;
    diff_hunk?: string | null;
    resolved: boolean;
  }>;
}

class DevHubProvider {
  constructor(private workspaceRoot: string) {}

  async getBundleContext(options?: {
    jiraKey?: string;
    prNumber?: number;
    branch?: string;
    includeComments?: boolean;
    includeDiff?: boolean;
    limit?: number;
    metadataOnly?: boolean;
  }): Promise<DevHubBundle> {
    const args = ['devhub_ide_bridge.py'];
    if (options?.jiraKey) args.push('--jira-key', options.jiraKey);
    if (options?.prNumber) args.push('--pr-number', String(options.prNumber));
    if (options?.branch) args.push('--branch', options.branch);
    if (options?.includeComments === false) args.push('--no-comments');
    if (options?.includeDiff === false) args.push('--no-diff');
    if (options?.metadataOnly) args.push('--metadata-only');
    if (options?.limit) args.push('--limit', String(options.limit));

    // Use uv to ensure environment consistency; fallback to system python if needed
    const cmd = 'uv';
    const cmdArgs = ['run', 'python', ...args];

    const { stdout } = await execFileAsync(cmd, cmdArgs, { cwd: this.workspaceRoot, maxBuffer: 10_000_000 });
    const data: DevHubBundle | { error?: string } = JSON.parse(stdout);
    if ((data as any)?.error) throw new Error((data as any).error);
    return data as DevHubBundle;
  }
}

export function activate(context: vscode.ExtensionContext) {
  const root = vscode.workspace.rootPath;
  if (!root) return;
  const devhub = new DevHubProvider(root);

  const disposable = vscode.commands.registerCommand('devhub.getCurrentContext', async () => {
    try {
      const bundle = await devhub.getBundleContext({ includeDiff: true, includeComments: true, limit: 20 });
      const doc = await vscode.workspace.openTextDocument({ content: JSON.stringify(bundle, null, 2), language: 'json' });
      await vscode.window.showTextDocument(doc);
      vscode.window.showInformationMessage(`DevHub: ${bundle?.metadata?.branch ?? 'unknown'} loaded`);
    } catch (e: any) {
      vscode.window.showErrorMessage(`DevHub error: ${e.message ?? e}`);
    }
  });

  context.subscriptions.push(disposable);
}
```

Step 3: Package.json command

```json
{
  "contributes": {
    "commands": [
      { "command": "devhub.getCurrentContext", "title": "DevHub: Get Current Context" }
    ]
  }
}
```

Notes
- The bridge mirrors SDK flags; no custom JSON CLI flags are required.
- Works cross-platform as long as uv and python are available; adjust the spawn if you prefer a venv python.

Guide 2 — Cursor IDE via Python SDK
Run a small helper that prints formatted context or raw JSON. Cursor can call this as a context provider or task.

Step 1: Add cursor_devhub.py

```python
# cursor_devhub.py
import argparse
import asyncio
import json
from typing import Any
from devhub.sdk import DevHubAsyncClient, ContextRequest
from returns.result import Success, Failure

async def fetch(req: ContextRequest) -> dict[str, Any]:
    async with DevHubAsyncClient() as client:
        res = await client.get_bundle_context(req)
    match res:
        case Success(b):
            return b.to_dict()
        case Failure(err):
            return {"error": err}

def format_for_agent(obj: dict[str, Any]) -> str:
    if 'error' in obj:
        return f"Error: {obj['error']}"
    md = []
    meta = obj.get('metadata', {})
    repo = meta.get('repository') or {}
    md.append(f"Repository: {repo.get('owner','?')}/{repo.get('name','?')}")
    md.append(f"Branch: {meta.get('branch','?')}")
    if jira := obj.get('jira'):
        md.append(f"\n## Jira {jira.get('key')}: {jira.get('summary')}")
        if jira.get('description'):
            md.append(jira['description'])
    if pr := obj.get('pull_request'):
        md.append(f"\n## PR #{pr.get('number')}: {pr.get('title')}")
        if pr.get('body'):
            md.append(pr['body'])
    if diff := obj.get('diff'):
        lines = diff.splitlines()
        md.append("\n## Code Changes (truncated)\n" + "\n".join(lines[:50] + (["..."] if len(lines) > 50 else [])))
    if comments := obj.get('comments'):
        md.append(f"\n## Review Comments ({len(comments)})")
        for c in comments[:5]:
            md.append(f"- {c.get('author','?')}: {c.get('body','')[:100]}...")
    return "\n".join(md)

async def run() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--jira-key')
    ap.add_argument('--pr-number', type=int)
    ap.add_argument('--branch')
    ap.add_argument('--no-diff', action='store_true')
    ap.add_argument('--no-comments', action='store_true')
    ap.add_argument('--limit', type=int, default=20)
    ap.add_argument('--raw-json', action='store_true')
    ns = ap.parse_args()

    req = ContextRequest(
        jira_key=ns.jira_key,
        pr_number=ns.pr_number,
        branch=ns.branch,
        include_diff=not ns.no_diff,
        include_comments=not ns.no_comments,
        comment_limit=ns.limit,
    )
    data = await fetch(req)
    if ns.raw_json:
        print(json.dumps(data, ensure_ascii=False))
    else:
        print(format_for_agent(data))
    return 0 if 'error' not in data else 1

if __name__ == '__main__':
    raise SystemExit(asyncio.run(run()))
```

Step 2: Cursor settings example

```json
{
  "cursor.general.enableContextProvider": true,
  "cursor.contextProviders": [
    {
      "name": "devhub-context",
      "command": "uv",
      "args": ["run", "python", "cursor_devhub.py"],
      "description": "DevHub current branch context"
    }
  ]
}
```

Tips
- Use --raw-json when you want to feed structured data to tools.
- Pass --jira-key or --pr-number for targeted context; otherwise branch auto-detection applies.

Validation notes
- Snippets use the final SDK (DevHubAsyncClient, ContextRequest) and returns Success/Failure pattern.
- The previous --format/--stdout CLI flags were removed because the production CLI writes files; the bridge scripts output JSON explicitly.
- TypeScript integration shells out to uv run python, ensuring your Python environment resolves devhub.
