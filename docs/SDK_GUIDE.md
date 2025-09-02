# DevHub Python SDK Guide

A concise guide to programmatic access using the async-first SDK. These examples reflect the final, tested APIs.

Prerequisites
- Python 3.13+
- In a git repository for real data
- GitHub CLI (gh) installed and authenticated
- Optional: JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN

Install
- If using uv: add devhub to your project and run examples with your environment active.

Quick start (recommended): DevHubAsyncClient
Use the async client as your primary interface; it initializes itself, is concurrency-friendly, and returns typed results via the returns library.

```python
import asyncio
from devhub.sdk import DevHubAsyncClient, ContextRequest
from returns.result import Success, Failure

async def main():
    # Auto-detect current repo/branch; request only what you need
    req = ContextRequest(include_diff=True, include_comments=True, comment_limit=20)

    async with DevHubAsyncClient() as client:
        result = await client.get_bundle_context(req)

    # Handle Success / Failure explicitly
    match result:
        case Success(bundle):
            print(f"Repo: {bundle.repository.owner}/{bundle.repository.name}")
            print(f"Branch: {bundle.branch}")
            if bundle.jira_issue:
                print(f"Jira: {bundle.jira_issue.key} - {bundle.jira_issue.summary}")
            if bundle.pr_data:
                print(f"PR: #{bundle.pr_data.get('number')} - {bundle.pr_data.get('title')}")
            if bundle.pr_diff:
                print(f"Diff length: {len(bundle.pr_diff)} chars")
            print(f"Unresolved comments: {len(bundle.comments)}")
        case Failure(error):
            print(f"Error: {error}")

if __name__ == "__main__":
    asyncio.run(main())
```

Handling results with returns
The SDK uses returns.result.Result. You can either pattern match or use isinstance checks.

```python
from returns.result import Success, Failure

# Pattern matching (Python 3.10+)
match result:
    case Success(value):
        ...  # use value
    case Failure(error):
        ...  # handle error string

# isinstance style
if isinstance(result, Success):
    value = result.unwrap()
else:  # Failure
    print(result.failure())
```

Request options (ContextRequest)
- jira_key: str | None
- pr_number: int | None
- branch: str | None
- include_jira/pr/diff/comments: bool
- comment_limit: int (default 20)
- metadata_only: bool (omit heavy content)

Common recipes
1) Current branch context, minimal metadata
```python
req = ContextRequest(metadata_only=True)
async with DevHubAsyncClient() as client:
    result = await client.get_bundle_context(req)
```

2) Force Jira context for a specific issue
```python
req = ContextRequest(jira_key="PROJ-123", include_diff=False, include_comments=False)
async with DevHubAsyncClient() as client:
    result = await client.get_bundle_context(req)
```

3) Specific PR with full details
```python
req = ContextRequest(pr_number=456, include_diff=True, include_comments=True, comment_limit=50)
async with DevHubAsyncClient() as client:
    result = await client.get_bundle_context(req)
```

Concurrency: fetch multiple contexts
```python
import asyncio
from devhub.sdk import DevHubAsyncClient, ContextRequest
from returns.result import Success, Failure

async def fetch_many():
    requests = [
        ContextRequest(jira_key="PROJ-123"),
        ContextRequest(pr_number=789),
        ContextRequest(branch="main", metadata_only=True),
    ]
    async with DevHubAsyncClient() as client:
        results = await client.get_multiple_contexts(requests)

    for idx, res in enumerate(results):
        if isinstance(res, Success):
            bundle = res.unwrap()
            print(f"[{idx}] {bundle.repository.name}@{bundle.branch}")
        else:
            print(f"[{idx}] Error: {res.failure()}")

asyncio.run(fetch_many())
```

Caching and timeouts (SDKConfig)
```python
import asyncio
from devhub.sdk import DevHubAsyncClient, SDKConfig, ContextRequest
from returns.result import Success

async def cached():
    cfg = SDKConfig(cache_enabled=True, cache_ttl_seconds=600, timeout_seconds=30)
    async with DevHubAsyncClient(cfg) as client:
        req = ContextRequest(jira_key="PROJ-123")
        first = await client.get_bundle_context(req)   # cache miss
        second = await client.get_bundle_context(req)  # cache hit
        if isinstance(second, Success):
            print("Returned from cache")

asyncio.run(cached())
```

Convenience functions
```python
import asyncio
from returns.result import Success
from devhub.sdk import get_current_context, get_context_for_jira, get_context_for_pr

async def examples():
    res1 = await get_current_context()
    res2 = await get_context_for_jira("PROJ-123")
    res3 = await get_context_for_pr(456)
    for r in (res1, res2, res3):
        if isinstance(r, Success):
            b = r.unwrap()
            print(b.repository.name, b.branch)

asyncio.run(examples())
```

CLI interop (optional)
If you must drive the CLI from code (e.g., in automation), use execute_cli_command. Note the CLI writes files and does not print JSON to stdout.

```python
import asyncio
from devhub.sdk import DevHubClient
from returns.result import Success, Failure

async def run_cli():
    client = DevHubClient()
    # Example: create a bundle in review-bundles/, using CLI defaults
    result = await client.execute_cli_command(["bundle"])  # returns CLI stdout/stderr text
    match result:
        case Success(output):
            print("CLI finished:", output.strip())
        case Failure(error):
            print("CLI error:", error)

asyncio.run(run_cli())
```

Best practices
- Prefer DevHubAsyncClient and explicit Success/Failure handling.
- Request only the data you need (toggle include_* flags and comment_limit).
- For real-time/agent loops, enable caching with a sensible TTL to avoid API rate limits.
- Initialize credentials/env once for stable runs; surface errors to logs and continue gracefully.

Troubleshooting
- Not in a git repo: ensure you run from within a repository.
- gh not authenticated: run `gh auth login`.
- Jira credentials missing: set JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN or configure via DevHub config.
