    pr_number=456,
    include_jira=False,
async def error_handling_example():
    comment_limit=50
)
    # Pattern 1: Check result type

# Get current branch with minimal data

```python
        # Use bundle data
        print(f"Success: {bundle.repository.name}")
from devhub.sdk import DevHubClient, ContextRequest, SDKConfig
        error_msg = result.failure()
        print(f"Error: {error_msg}")
    
    # Pattern 2: Chain operations
    request = ContextRequest(jira_key="INVALID-123")
    result = await client.get_bundle_context(request)
    if isinstance(init_result, Failure):
    match result:
        case Success(bundle):
            print(f"Got bundle for {bundle.branch}")
        case Failure(error):
            print(f"Operation failed: {error}")
        include_jira=True,
    # Pattern 3: Fallback handling
        include_diff=True,
    
    if isinstance(jira_result, Failure):
        print(f"Jira fetch failed: {jira_result.failure()}")
        # Try alternative approach
        bundle_result = await client.get_bundle_context(
            ContextRequest(include_jira=False)
        )
        if isinstance(bundle_result, Success):
            print("Fallback successful: got context without Jira")
        if bundle.jira_issue:
asyncio.run(error_handling_example())
```
            print(f"Summary: {bundle.jira_issue.summary}")
### Caching Configuration
        if bundle.pr_data:
            print(f"PR Number: {bundle.pr_data.get('number')}")
import asyncio
from devhub.sdk import DevHubClient, SDKConfig, ContextRequest
        if bundle.comments:
async def caching_example():
    else:
        print(f"Error: {result.failure()}")

        cache_ttl_seconds=600  # 10 minutes
```

#### DevHubAsyncClient
    request = ContextRequest(jira_key="PROJ-123")
    

    print("First call (cache miss)...")
    result1 = await client.get_bundle_context(request)
    
    # Second call - returns from cache
    print("Second call (cache hit)...")
    result2 = await client.get_bundle_context(request)

    # Disable caching
    no_cache_config = SDKConfig(cache_enabled=False)
    no_cache_client = DevHubClient(no_cache_config)
from devhub.sdk import DevHubAsyncClient, ContextRequest
    print("No cache call (always fresh)...")
    result3 = await no_cache_client.get_bundle_context(request)

asyncio.run(caching_example())
        # Get single context
        request = ContextRequest(jira_key="PROJ-123")
## Convenience Functions

For quick access, use the convenience functions:
        
        if isinstance(result, Success):
            bundle = result.unwrap()
from devhub.sdk import get_current_context, get_context_for_jira, get_context_for_pr
    client = DevHubClient()
    
async def convenience_examples():
    # Get current branch context
    current = await get_current_context()
    if isinstance(current, Success):
        bundle = current.unwrap()
        print(f"Current: {bundle.repository.name}@{bundle.branch}")
        issue = result.unwrap()
    # Get context for specific Jira issue
    jira_context = await get_context_for_jira("PROJ-123")
    if isinstance(jira_context, Success):
        bundle = jira_context.unwrap()
        if bundle.jira_issue:
            print(f"Jira: {bundle.jira_issue.summary}")
    
    # Get context for specific PR
    pr_context = await get_context_for_pr(456)
    if isinstance(pr_context, Success):
        bundle = pr_context.unwrap()
        if bundle.pr_data:
            print(f"PR: {bundle.pr_data.get('title', 'N/A')}")
import asyncio
asyncio.run(convenience_examples())
        print(f"Title: {pr_data.get('title', 'N/A')}")
        if 'diff' in pr_data:
            print(f"Diff length: {len(pr_data['diff'])} characters")
    
### 1. Always Handle Results
```python
import asyncio
# ✅ Good

async def streaming_example():
    client = DevHubClient()
    # Use bundle
    # Stream PR updates (runs indefinitely)
    logger.error(f"Failed: {result.failure()}")
        async for update in client.stream_pr_updates(456):
# ❌ Bad - no error handling
bundle = (await client.get_bundle_context()).unwrap()  # May raise!
            print(f"Data: {update.data}")
            
### 2. Use Appropriate Configuration
            if update_count >= 5:  # Stop after 5 updates for example
                break
# ✅ Good - configure for your use case
config = SDKConfig(
    organization="my-org",           # Set your organization
    cache_enabled=True,              # Enable caching for performance
    cache_ttl_seconds=300,           # Reasonable TTL
    timeout_seconds=30               # Reasonable timeout
)
        print("Streaming stopped by user")
# ❌ Bad - using defaults when you need specific behavior
client = DevHubClient()  # May not work for your organization
### CLI Command Execution

### 3. Use Context Managers for Async Client
import asyncio
from devhub.sdk import DevHubClient
# ✅ Good - proper cleanup
async with DevHubAsyncClient() as client:
    result = await client.get_bundle_context()

# ❌ Bad - manual management
client = DevHubAsyncClient()
await client.__aenter__()
# ... work with client
await client.__aexit__(None, None, None)
```

### 4. Specify Request Parameters

```python
# ✅ Good - explicit about what you need

    include_jira=True,
    include_pr=False,      # Skip if not needed
    include_diff=False,    # Skip large diffs if not needed
    include_comments=True,
    comment_limit=10       # Limit to what you need
    result = await client.execute_cli_command([
        "bundle", 
# ❌ Bad - getting everything when you only need some
request = ContextRequest()  # Gets everything, may be slow
    ])
    
### 5. Error Logging
        print(output)
    else:
import logging
from devhub.sdk import DevHubClient
from returns.result import Failure
    # Execute with timeout and no output capture
logger = logging.getLogger(__name__)
        capture_output=False,
async def robust_example():
    )
    
    result = await client.get_bundle_context()

    if isinstance(result, Failure):
        logger.error(f"DevHub SDK error: {result.failure()}")
        # Handle error appropriately
        return None
    
    return result.unwrap()
from devhub.sdk import DevHubClient, ContextRequest
        """Analyze current development context."""
## Integration Examples

### With FastAPI

```python
from fastapi import FastAPI, HTTPException
from devhub.sdk import get_context_for_jira
from returns.result import Success, Failure

app = FastAPI()

@app.get("/jira/{jira_key}")
async def get_jira_context(jira_key: str):
    result = await get_context_for_jira(jira_key)
    
    match result:
        case Success(bundle):
            return {
                "jira_key": bundle.jira_issue.key if bundle.jira_issue else None,
                "repository": f"{bundle.repository.owner}/{bundle.repository.name}",
                "branch": bundle.branch
            }
        case Failure(error):
            raise HTTPException(status_code=400, detail=error)
```

### With Background Tasks
        
        if isinstance(result, Success):
import asyncio
from devhub.sdk import DevHubClient
            analysis = {
async def background_monitor():
    """Background task to monitor PR updates."""
    client = DevHubClient()
    
    while True:
        try:
            async for update in client.stream_pr_updates(456):
                if update.update_type == "pr_updated":
                    # Process update
                    await process_pr_update(update.data)
                    
        except Exception as e:
            print(f"Monitor error: {e}")
            await asyncio.sleep(60)  # Wait before retry
                "complexity_score": self._calculate_complexity(bundle)
async def process_pr_update(pr_data):
    """Process a PR update."""
    print(f"Processing PR update: {pr_data}")
```
            
        else:
            return {"error": result.failure()}
    
    def _calculate_complexity(self, bundle: BundleData) -> float:
        """Calculate complexity score based on bundle data."""
        score = 0.0
        
        # Diff complexity
        if bundle.pr_diff:
            lines = len(bundle.pr_diff.split('\n'))
            score += min(lines / 100, 5.0)  # Max 5 points for diff size
        
        # Comment complexity
        score += len(bundle.comments) * 0.5  # 0.5 points per comment
        
        return min(score, 10.0)  # Max score of 10

async def ai_agent_example():
    agent = AICodeAgent()
    analysis = await agent.analyze_current_work()
    print(f"Analysis: {analysis}")
```

### Custom Tool Development

```python
from devhub.sdk import DevHubClient, SDKConfig
import json

class DevHubReportGenerator:
    """Custom tool for generating development reports."""
    
    def __init__(self, output_path: str):
        self.client = DevHubClient(SDKConfig(cache_enabled=True))
        self.output_path = output_path
    
    async def generate_weekly_report(self, jira_keys: list[str]) -> None:
        """Generate weekly development report."""
        report_data = []
        
        for jira_key in jira_keys:
            # Get context for each Jira issue
            result = await self.client.get_bundle_context(
                ContextRequest(jira_key=jira_key, include_diff=True)
            )
            
            if isinstance(result, Success):
                bundle = result.unwrap()
                
                # Extract report data
                item = {
                    "jira_key": jira_key,
                    "summary": bundle.jira_issue.summary if bundle.jira_issue else "Unknown",
                    "pr_number": bundle.pr_data.get("number") if bundle.pr_data else None,
                    "pr_status": bundle.pr_data.get("state") if bundle.pr_data else None,
                    "comment_count": len(bundle.comments),
                    "diff_lines": len(bundle.pr_diff.split('\n')) if bundle.pr_diff else 0
                }
                
                report_data.append(item)
        
        # Save report
        with open(self.output_path, 'w') as f:
            json.dump(report_data, f, indent=2)
        
        print(f"Report generated: {self.output_path}")

async def report_generator_example():
    generator = DevHubReportGenerator("weekly_report.json")
    await generator.generate_weekly_report(["PROJ-123", "PROJ-124", "PROJ-125"])
```

## Error Handling

### Result Pattern Usage

```python
from returns.result import Success, Failure

async def robust_error_handling():
    client = DevHubClient()
    
    result = await client.get_bundle_context()
    
    # Pattern matching (Python 3.10+)
    match result:
        case Success(bundle):
            print(f"Success: Got bundle for {bundle.branch}")
            # Process bundle data
        case Failure(error):
            print(f"Error: {error}")
            # Handle error appropriately
    
    # Traditional isinstance checking
    if isinstance(result, Success):
        bundle = result.unwrap()
        # Process success case
    elif isinstance(result, Failure):
        error = result.failure()
        # Handle error case
```

### Common Error Scenarios

```python
async def handle_common_errors():
    client = DevHubClient()
    
    # Handle missing repository
    result = await client.get_current_branch_context()
    if isinstance(result, Failure) and "repository" in result.failure():
        print("Not in a git repository - please run from a git project")
        return
    
    # Handle missing Jira credentials
    jira_result = await client.get_jira_issue("PROJ-123")
    if isinstance(jira_result, Failure) and "credentials" in jira_result.failure():
        print("Jira credentials not configured - please set JIRA_EMAIL and JIRA_API_TOKEN")
        return
    
    # Handle network timeouts
    try:
        pr_result = await client.get_pr_details(456)
    except asyncio.TimeoutError:
        print("Request timed out - please check network connection")
```

## Performance Optimization

### Caching Strategies

```python
from devhub.sdk import DevHubClient, SDKConfig

async def caching_examples():
    # Enable caching with custom TTL
    config = SDKConfig(
        cache_enabled=True,
        cache_ttl_seconds=900,  # 15 minutes
    )
    client = DevHubClient(config)
    
    # First call - fetches from API
    result1 = await client.get_bundle_context()
    
    # Second call - returns cached result (if within TTL)
    result2 = await client.get_bundle_context()
    
    # Different request - not cached
    result3 = await client.get_bundle_context(
        ContextRequest(comment_limit=50)
    )
```

### Concurrent Operations

```python
import asyncio
from devhub.sdk import DevHubAsyncClient, ContextRequest

async def concurrent_operations():
    async with DevHubAsyncClient() as client:
        # Concurrent requests for different data
        tasks = [
            client.get_bundle_context(ContextRequest(jira_key="PROJ-123")),
            client.get_bundle_context(ContextRequest(pr_number=456)),
            client.get_bundle_context(ContextRequest(branch="main")),
        ]
        
        # Execute all requests concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"Task {i} failed: {result}")
            elif isinstance(result, Success):
                bundle = result.unwrap()
                print(f"Task {i} success: {bundle.branch}")
            else:
                print(f"Task {i} error: {result.failure()}")
```

## Testing

### Unit Testing

```python
import pytest
from unittest.mock import AsyncMock, patch
from devhub.sdk import DevHubClient
from returns.result import Success

@pytest.mark.asyncio
async def test_get_bundle_context():
    """Test bundle context retrieval."""
    client = DevHubClient()
    
    # Mock the underlying functions
    with patch('devhub.sdk.get_repository_info') as mock_repo, \
         patch('devhub.sdk.get_current_branch') as mock_branch:
        
        mock_repo.return_value = Success(Repository(owner="test", name="repo"))
        mock_branch.return_value = Success("main")
        
        result = await client.get_current_branch_context()
        
        assert isinstance(result, Success)
        bundle = result.unwrap()
        assert bundle.repository.owner == "test"
        assert bundle.branch == "main"

@pytest.mark.asyncio 
async def test_error_handling():
    """Test error handling in SDK."""
    client = DevHubClient()
    
    with patch('devhub.sdk.get_repository_info') as mock_repo:
        mock_repo.return_value = Failure("Repository not found")
        
        result = await client.get_current_branch_context()
        
        assert isinstance(result, Failure)
        assert "Repository not found" in result.failure()
```

## Best Practices

### 1. Use Async Context Managers

```python
# Preferred
async with DevHubAsyncClient() as client:
    result = await client.get_bundle_context()

# Instead of
client = DevHubClient()
await client.initialize()
result = await client.get_bundle_context()
```

### 2. Handle Results Properly

```python
# Good - explicit error handling
result = await client.get_bundle_context()
if isinstance(result, Success):
    bundle = result.unwrap()
    # Process bundle
else:
    logger.error(f"Failed to get context: {result.failure()}")
    return None

# Avoid - assumes success
bundle = result.unwrap()  # May raise exception
```

### 3. Configure Caching Appropriately

```python
# For real-time applications - disable caching
config = SDKConfig(cache_enabled=False)

# For batch processing - longer cache TTL
config = SDKConfig(cache_ttl_seconds=3600)  # 1 hour

# For development - shorter cache TTL
config = SDKConfig(cache_ttl_seconds=60)  # 1 minute
```

### 4. Use Specific Context Requests

```python
# Good - specific request
request = ContextRequest(
    jira_key="PROJ-123",
    include_diff=False,  # Skip if not needed
    comment_limit=10,    # Limit data
    metadata_only=True   # For lightweight requests
)

# Less efficient - default request with everything
request = ContextRequest()  # Includes all data
```

## Migration Guide

### From CLI to SDK

```python
# CLI Command:
# devhub bundle --jira-key PROJ-123 --format json

# SDK Equivalent:
from devhub.sdk import DevHubClient, ContextRequest

async def cli_to_sdk():
    client = DevHubClient()
    result = await client.get_bundle_context(
        ContextRequest(jira_key="PROJ-123")
    )
    
    if isinstance(result, Success):
        bundle = result.unwrap()
        # Use bundle.to_dict() to get JSON-like data
        data = bundle.to_dict()
```

### From MCP to SDK

```python
# MCP Tool Call:
# get-bundle-context(jira_key="PROJ-123", include_diff=true)

# SDK Equivalent:
async def mcp_to_sdk():
    result = await get_context_for_jira("PROJ-123")
    # Same result structure, but as typed Python objects
```

---

The DevHub Python SDK provides a powerful, type-safe interface for building AI agents and custom development tools. Its functional programming foundation ensures reliable, predictable behavior while maintaining the flexibility needed for complex development workflows.