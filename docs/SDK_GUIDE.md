# DevHub Python SDK Guide

A comprehensive guide to programmatic access using the async-first DevHubClient. All examples are tested and ready to use with the final API.

## Prerequisites

- **Python 3.13+**
- **Git repository** for real data access
- **GitHub CLI (`gh`)** installed and authenticated
- **Optional**: Jira credentials via environment variables:
  - `JIRA_BASE_URL` (e.g., https://your-domain.atlassian.net)
  - `JIRA_EMAIL` (e.g., your.email@company.com)
  - `JIRA_API_TOKEN` (your Jira API token)

## Installation

```bash
# Install DevHub
pip install devhub
# or
uv add devhub

# Verify installation
python -c "from devhub.sdk import DevHubClient; print('SDK ready')"
```

## Quick Start: DevHubClient

The `DevHubClient` is the primary interface for programmatic access. It's async-first, handles initialization automatically, and returns typed `Result` objects for explicit error handling.

### Basic Usage

```python
import asyncio
from devhub.sdk import DevHubClient, ContextRequest
from returns.result import Success, Failure

async def main():
    # Create client and initialize
    client = DevHubClient()
    await client.initialize()
    
    # Auto-detect current repo/branch context
    request = ContextRequest(
        include_diff=True,
        include_comments=True,
        comment_limit=20
    )
    
    result = await client.get_bundle_context(request)
    
    # Handle Success/Failure explicitly
    match result:
        case Success(bundle):
            print(f"Repository: {bundle.repository.owner}/{bundle.repository.name}")
            print(f"Branch: {bundle.branch}")
            if bundle.jira_issue:
                print(f"Jira: {bundle.jira_issue.key} - {bundle.jira_issue.summary}")
            if bundle.pr_data:
                print(f"PR: #{bundle.pr_data.get('number')} - {bundle.pr_data.get('title')}")
            if bundle.pr_diff:
                print(f"Diff length: {len(bundle.pr_diff)} characters")
            print(f"Unresolved comments: {len(bundle.comments)}")
        case Failure(error):
            print(f"Error: {error}")

if __name__ == "__main__":
    asyncio.run(main())
```

### Specific Issue/PR Context

```python
import asyncio
from devhub.sdk import DevHubClient, ContextRequest
from returns.result import Success, Failure

async def get_specific_context():
    client = DevHubClient()
    await client.initialize()
    
    # Request specific Jira issue with full context
    request = ContextRequest(
        jira_key="PROJ-123",
        include_jira=True,
        include_pr=True,
        include_diff=True,
        include_comments=True,
        comment_limit=50
    )
    
    result = await client.get_bundle_context(request)
    
    if isinstance(result, Success):
        bundle = result.unwrap()
        
        # Access structured data
        if bundle.jira_issue:
            print(f"Jira Issue: {bundle.jira_issue.key}")
            print(f"Summary: {bundle.jira_issue.summary}")
            print(f"Status: {bundle.jira_issue.status}")
            print(f"Assignee: {bundle.jira_issue.assignee}")
        
        if bundle.pr_data:
            pr = bundle.pr_data
            print(f"PR #{pr.get('number')}: {pr.get('title')}")
            print(f"State: {pr.get('state')}")
            print(f"Author: {pr.get('user', {}).get('login')}")
        
        # Process unresolved comments
        for comment in bundle.comments:
            print(f"Comment by {comment.author}: {comment.body[:100]}...")
    
    else:
        print(f"Failed to get context: {result.failure()}")

asyncio.run(get_specific_context())
```

### Selective Data Inclusion

```python
import asyncio
from devhub.sdk import DevHubClient, ContextRequest

async def metadata_only_example():
    """Get only metadata without large content like diffs."""
    client = DevHubClient()
    await client.initialize()
    
    # Request only metadata, no diff content
    request = ContextRequest(
        pr_number=456,
        include_jira=True,
        include_pr=True,
        include_diff=False,  # Skip diff for faster response
        include_comments=True,
        comment_limit=10,
        metadata_only=True  # Only metadata, no full content
    )
    
    result = await client.get_bundle_context(request)
    
    if isinstance(result, Success):
        bundle = result.unwrap()
        print(f"Quick metadata for PR #{bundle.pr_data.get('number') if bundle.pr_data else 'N/A'}")
        print(f"Comments: {len(bundle.comments)} unresolved")
        # bundle.pr_diff will be None due to include_diff=False
    
    return result

asyncio.run(metadata_only_example())
```

## Advanced Usage

### Configuration and Caching

```python
import asyncio
from pathlib import Path
from devhub.sdk import DevHubClient, SDKConfig, ContextRequest

async def configured_client_example():
    # Custom SDK configuration
    config = SDKConfig(
        workspace_path=Path("/path/to/your/repo"),
        organization="your-github-org",
        cache_enabled=True,
        cache_ttl_seconds=600,  # 10 minutes cache
        timeout_seconds=60
    )
    
    client = DevHubClient(config)
    await client.initialize()
    
    # First request - will hit APIs
    request = ContextRequest(jira_key="PROJ-789")
    result1 = await client.get_bundle_context(request)
    
    # Second identical request - will use cache
    result2 = await client.get_bundle_context(request)
    
    # Both results should be identical
    assert result1.map(lambda x: x.jira_issue.key if x.jira_issue else None) == \
           result2.map(lambda x: x.jira_issue.key if x.jira_issue else None)

asyncio.run(configured_client_example())
```

### Error Handling Patterns

```python
import asyncio
from devhub.sdk import DevHubClient, ContextRequest
from returns.result import Success, Failure

async def robust_error_handling():
    client = DevHubClient()
    
    # Initialize with error handling
    init_result = await client.initialize()
    if isinstance(init_result, Failure):
        print(f"Failed to initialize: {init_result.failure()}")
        return
    
    # Request with potential for errors
    request = ContextRequest(
        jira_key="INVALID-KEY",  # This might fail
        pr_number=99999,        # This might not exist
    )
    
    result = await client.get_bundle_context(request)
    
    # Pattern matching for clean error handling
    match result:
        case Success(bundle):
            # Success case - process the bundle
            print("Successfully retrieved context")
            if bundle.jira_issue:
                print(f"Jira: {bundle.jira_issue.key}")
            else:
                print("No Jira issue found (this is okay)")
                
        case Failure(error):
            # Error case - handle gracefully
            print(f"Context retrieval failed: {error}")
            
            # You might want to retry, log, or fallback
            if "authentication" in error.lower():
                print("Check your GitHub CLI authentication: gh auth status")
            elif "jira" in error.lower():
                print("Check your Jira credentials")

asyncio.run(robust_error_handling())
```

### Working with Bundle Data

```python
import asyncio
import json
from devhub.sdk import DevHubClient, ContextRequest
from returns.result import Success

async def process_bundle_data():
    client = DevHubClient()
    await client.initialize()
    
    request = ContextRequest(jira_key="PROJ-123")
    result = await client.get_bundle_context(request)
    
    if isinstance(result, Success):
        bundle = result.unwrap()
        
        # Access repository information
        repo = bundle.repository
        print(f"Working with: {repo.owner}/{repo.name}")
        print(f"Clone URL: {repo.clone_url}")
        print(f"Default branch: {repo.default_branch}")
        
        # Process Jira issue data
        if bundle.jira_issue:
            issue = bundle.jira_issue
            print(f"\nJira Issue Analysis:")
            print(f"  Key: {issue.key}")
            print(f"  Type: {issue.issue_type}")
            print(f"  Priority: {issue.priority}")
            print(f"  Components: {', '.join(issue.components)}")
            print(f"  Labels: {', '.join(issue.labels)}")
        
        # Analyze PR data
        if bundle.pr_data:
            pr = bundle.pr_data
            print(f"\nPR Analysis:")
            print(f"  Mergeable: {pr.get('mergeable')}")
            print(f"  Checks: {pr.get('mergeable_state')}")
            print(f"  Files changed: {pr.get('changed_files', 0)}")
            print(f"  Additions: +{pr.get('additions', 0)}")
            print(f"  Deletions: -{pr.get('deletions', 0)}")
        
        # Process comments for action items
        if bundle.comments:
            print(f"\nUnresolved Comments ({len(bundle.comments)}):")
            for comment in bundle.comments[:5]:  # Show first 5
                print(f"  @{comment.author}: {comment.body[:80]}...")
        
        # Convert to JSON for external processing
        bundle_dict = {
            "repository": {
                "owner": repo.owner,
                "name": repo.name,
                "clone_url": repo.clone_url
            },
            "branch": bundle.branch,
            "jira_key": bundle.jira_issue.key if bundle.jira_issue else None,
            "pr_number": bundle.pr_data.get("number") if bundle.pr_data else None,
            "comment_count": len(bundle.comments),
            "has_diff": bool(bundle.pr_diff)
        }
        
        print(f"\nBundle Summary JSON:")
        print(json.dumps(bundle_dict, indent=2))

asyncio.run(process_bundle_data())
```

## Result Type Handling

DevHub uses the `returns` library for explicit error handling. Here are the key patterns:

### Pattern Matching (Recommended)

```python
from returns.result import Success, Failure

result = await client.get_bundle_context(request)

match result:
    case Success(bundle):
        # Handle success
        process_bundle(bundle)
    case Failure(error):
        # Handle error
        log_error(error)
```

### isinstance Checks

```python
if isinstance(result, Success):
    bundle = result.unwrap()
    # Process bundle
elif isinstance(result, Failure):
    error = result.failure()
    # Handle error
```

### Chaining Operations

```python
# Chain operations with map
result = await client.get_bundle_context(request)
summary = result.map(lambda bundle: f"PR #{bundle.pr_data.get('number') if bundle.pr_data else 'N/A'}")

# Use bind for operations that return Results
def get_comment_count(bundle):
    return Success(len(bundle.comments))

comment_result = result.bind(get_comment_count)
```

## Configuration

### Environment Variables

```bash
# Jira integration (optional)
export JIRA_BASE_URL="https://your-domain.atlassian.net"
export JIRA_EMAIL="your.email@company.com"
export JIRA_API_TOKEN="your-api-token"

# GitHub (required for PR data)
export GITHUB_TOKEN="ghp_your_token_here"
```

### SDK Configuration Options

```python
from devhub.sdk import SDKConfig

config = SDKConfig(
    workspace_path=Path.cwd(),     # Working directory
    organization="your-org",        # GitHub organization
    cache_enabled=True,            # Enable response caching
    cache_ttl_seconds=300,         # Cache lifetime (5 minutes)
    timeout_seconds=30             # Request timeout
)
```

## Testing Your Integration

```python
import asyncio
from devhub.sdk import DevHubClient, ContextRequest

async def test_integration():
    """Test your DevHub SDK integration."""
    try:
        client = DevHubClient()
        
        # Test initialization
        init_result = await client.initialize()
        assert isinstance(init_result, Success), f"Init failed: {init_result.failure()}"
        print("✓ Client initialization successful")
        
        # Test basic context retrieval
        request = ContextRequest(include_diff=False)  # Quick test
        result = await client.get_bundle_context(request)
        
        if isinstance(result, Success):
            bundle = result.unwrap()
            print("✓ Context retrieval successful")
            print(f"  Repository: {bundle.repository.owner}/{bundle.repository.name}")
            print(f"  Branch: {bundle.branch}")
        else:
            print(f"✗ Context retrieval failed: {result.failure()}")
            
    except Exception as e:
        print(f"✗ Integration test failed: {e}")

# Run the test
asyncio.run(test_integration())
```

## Common Use Cases

### Code Review Assistant

```python
async def code_review_assistant(jira_key: str):
    """Gather context for code review."""
    client = DevHubClient()
    await client.initialize()
    
    request = ContextRequest(
        jira_key=jira_key,
        include_diff=True,
        include_comments=True,
        comment_limit=100
    )
    
    result = await client.get_bundle_context(request)
    
    if isinstance(result, Success):
        bundle = result.unwrap()
        
        # Generate review summary
        summary = {
            "issue": bundle.jira_issue.summary if bundle.jira_issue else "No Jira issue",
            "pr_title": bundle.pr_data.get("title") if bundle.pr_data else "No PR",
            "files_changed": bundle.pr_data.get("changed_files", 0) if bundle.pr_data else 0,
            "unresolved_comments": len(bundle.comments),
            "diff_size": len(bundle.pr_diff) if bundle.pr_diff else 0
        }
        
        return summary
    
    return {"error": result.failure()}
```

### Branch Analysis

```python
async def analyze_current_branch():
    """Analyze the current git branch context."""
    client = DevHubClient()
    await client.initialize()
    
    # Auto-detect everything from current branch
    request = ContextRequest()
    result = await client.get_bundle_context(request)
    
    if isinstance(result, Success):
        bundle = result.unwrap()
        
        analysis = {
            "branch": bundle.branch,
            "has_jira_issue": bundle.jira_issue is not None,
            "has_open_pr": bundle.pr_data is not None,
            "needs_attention": len(bundle.comments) > 0
        }
        
        if analysis["needs_attention"]:
            analysis["comment_authors"] = list({c.author for c in bundle.comments})
        
        return analysis
    
    return {"error": result.failure()}
```

This SDK guide provides everything needed to integrate DevHub into your development workflow programmatically. The async-first design ensures high performance, while the Result types provide explicit error handling for robust applications.
