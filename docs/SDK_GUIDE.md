# DevHub Python SDK Guide

> **Complete guide for the DevHub Python SDK for programmatic access**

The DevHub Python SDK provides a clean, type-safe interface for AI agents and custom tools to access DevHub functionality programmatically. Built on functional programming principles, it offers both synchronous and asynchronous APIs with comprehensive error handling and caching support.

## Quick Start

### Installation

```python
# DevHub SDK is included with DevHub installation
from devhub.sdk import DevHubClient, ContextRequest

# Create client
client = DevHubClient()
```

### Simple Usage

```python
import asyncio
from devhub.sdk import get_current_context

async def main():
    # Get current branch context
    result = await get_current_context()
    
    if isinstance(result, Success):
        bundle = result.unwrap()
        print(f"Repository: {bundle.repository.owner}/{bundle.repository.name}")
        print(f"Branch: {bundle.branch}")
        if bundle.jira_issue:
            print(f"Jira: {bundle.jira_issue.key} - {bundle.jira_issue.summary}")
    else:
        print(f"Error: {result.failure()}")

asyncio.run(main())
```

## API Reference

### Core Classes

#### DevHubClient

Main synchronous client for DevHub access.

```python
class DevHubClient:
    def __init__(self, config: Optional[SDKConfig] = None) -> None
    
    async def initialize(self) -> Result[None, str]
    async def get_bundle_context(self, request: Optional[ContextRequest] = None) -> Result[BundleData, str]
    async def get_jira_issue(self, jira_key: str) -> Result[JiraIssue, str]
    async def get_pr_details(self, pr_number: int, include_diff: bool = True) -> Result[dict[str, Any], str]
    async def get_pr_comments(self, pr_number: int, limit: int = 20) -> Result[tuple[ReviewComment, ...], str]
    async def get_current_branch_context(self, include_diff: bool = True, include_comments: bool = True, comment_limit: int = 20) -> Result[BundleData, str]
    async def stream_pr_updates(self, pr_number: int) -> AsyncIterator[StreamUpdate]
    async def execute_cli_command(self, command: list[str], capture_output: bool = True) -> Result[str, str]
```

#### DevHubAsyncClient

Async-first client with context manager support.

```python
class DevHubAsyncClient:
    def __init__(self, config: Optional[SDKConfig] = None) -> None
    
    async def __aenter__(self) -> "DevHubAsyncClient"
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None
    
    async def get_bundle_context(self, request: Optional[ContextRequest] = None) -> Result[BundleData, str]
    async def get_multiple_contexts(self, requests: list[ContextRequest]) -> list[Result[BundleData, str]]
    async def stream_updates(self, pr_number: int) -> AsyncIterator[StreamUpdate]
```

### Configuration Classes

#### SDKConfig

```python
@dataclass(frozen=True, slots=True)
class SDKConfig:
    workspace_path: Path = field(default_factory=Path.cwd)
    organization: Optional[str] = None
    cache_enabled: bool = True
    cache_ttl_seconds: int = 300
    timeout_seconds: int = 30
```

#### ContextRequest

```python
@dataclass(frozen=True, slots=True)
class ContextRequest:
    jira_key: Optional[str] = None
    pr_number: Optional[int] = None
    branch: Optional[str] = None
    include_jira: bool = True
    include_pr: bool = True
    include_diff: bool = True
    include_comments: bool = True
    comment_limit: int = 20
    metadata_only: bool = False
```

## Usage Examples

### Basic Operations

#### Get Current Branch Context

```python
import asyncio
from devhub.sdk import DevHubClient

async def get_current_context():
    client = DevHubClient()
    
    result = await client.get_current_branch_context(
        include_diff=True,
        include_comments=True,
        comment_limit=15
    )
    
    if isinstance(result, Success):
        bundle = result.unwrap()
        
        # Access repository info
        repo = bundle.repository
        print(f"Repository: {repo.owner}/{repo.name}")
        
        # Access Jira info
        if bundle.jira_issue:
            jira = bundle.jira_issue
            print(f"Jira: {jira.key} - {jira.summary}")
        
        # Access PR info
        if bundle.pr_data:
            pr = bundle.pr_data
            print(f"PR: #{pr['number']} - {pr['title']}")
        
        # Access comments
        if bundle.comments:
            print(f"Comments: {len(bundle.comments)} unresolved")
            for comment in bundle.comments[:3]:  # First 3 comments
                print(f"  - {comment.author}: {comment.body[:50]}...")
        
        # Access diff
        if bundle.pr_diff:
            lines = bundle.pr_diff.split('\n')
            print(f"Diff: {len(lines)} lines changed")
    
    else:
        print(f"Error: {result.failure()}")

asyncio.run(get_current_context())
```

#### Get Specific Jira Issue

```python
async def get_jira_issue():
    client = DevHubClient()
    
    result = await client.get_jira_issue("PROJ-123")
    
    if isinstance(result, Success):
        issue = result.unwrap()
        print(f"Key: {issue.key}")
        print(f"Summary: {issue.summary}")
        print(f"Description: {issue.description}")
    else:
        print(f"Error: {result.failure()}")
```

#### Get PR Details with Diff

```python
async def get_pr_details():
    client = DevHubClient()
    
    result = await client.get_pr_details(456, include_diff=True)
    
    if isinstance(result, Success):
        pr_data = result.unwrap()
        print(f"PR #{pr_data['number']}: {pr_data['title']}")
        print(f"Author: {pr_data['user']['login']}")
        print(f"Created: {pr_data['created_at']}")
        
        if 'diff' in pr_data:
            print(f"Diff: {len(pr_data['diff'].split('\\n'))} lines")
    else:
        print(f"Error: {result.failure()}")
```

### Advanced Usage

#### Custom Configuration

```python
from devhub.sdk import DevHubClient, SDKConfig
from pathlib import Path

async def custom_config_example():
    # Create custom configuration
    config = SDKConfig(
        workspace_path=Path("/path/to/project"),
        organization="my-org",
        cache_enabled=True,
        cache_ttl_seconds=600,  # 10 minutes
        timeout_seconds=60
    )
    
    client = DevHubClient(config)
    
    # Use client with custom configuration
    result = await client.get_current_branch_context()
    # ... handle result
```

#### Async Context Manager

```python
from devhub.sdk import DevHubAsyncClient, ContextRequest

async def async_context_example():
    async with DevHubAsyncClient() as client:
        # Multiple concurrent requests
        requests = [
            ContextRequest(jira_key="PROJ-123"),
            ContextRequest(pr_number=456),
            ContextRequest(branch="feature/test")
        ]
        
        results = await client.get_multiple_contexts(requests)
        
        for i, result in enumerate(results):
            if isinstance(result, Success):
                bundle = result.unwrap()
                print(f"Request {i}: Success - {bundle.branch}")
            else:
                print(f"Request {i}: Error - {result.failure()}")
```

#### Streaming Updates

```python
async def stream_pr_updates():
    client = DevHubClient()
    
    # Stream updates for PR #789
    async for update in client.stream_pr_updates(789):
        print(f"Update type: {update.update_type}")
        print(f"Timestamp: {update.timestamp}")
        print(f"Data: {update.data.get('title', 'Unknown')}")
        
        # Process update
        if update.update_type == "pr_updated":
            # Handle PR update
            pass
```

#### CLI Command Execution

```python
async def execute_cli_commands():
    client = DevHubClient()
    
    # Execute custom DevHub CLI command
    result = await client.execute_cli_command([
        "bundle", 
        "--jira-key", "PROJ-123",
        "--format", "json",
        "--limit", "10"
    ])
    
    if isinstance(result, Success):
        output = result.unwrap()
        print(f"CLI Output: {output[:100]}...")
    else:
        print(f"CLI Error: {result.failure()}")
```

### Convenience Functions

#### Quick Access Functions

```python
from devhub.sdk import get_current_context, get_context_for_jira, get_context_for_pr

async def quick_access_examples():
    # Get current context
    current = await get_current_context()
    
    # Get context for specific Jira issue
    jira_context = await get_context_for_jira("PROJ-123")
    
    # Get context for specific PR
    pr_context = await get_context_for_pr(456)
    
    # All return Result[BundleData, str]
    for result in [current, jira_context, pr_context]:
        if isinstance(result, Success):
            bundle = result.unwrap()
            print(f"Bundle for {bundle.branch}: {len(bundle.comments)} comments")
```

## Integration Patterns

### AI Agent Integration

```python
from devhub.sdk import DevHubClient, ContextRequest
from typing import Dict, Any

class AICodeAgent:
    """Example AI code agent using DevHub SDK."""
    
    def __init__(self):
        self.devhub = DevHubClient()
    
    async def analyze_current_work(self) -> Dict[str, Any]:
        """Analyze current development context."""
        result = await self.devhub.get_current_branch_context()
        
        if isinstance(result, Success):
            bundle = result.unwrap()
            
            analysis = {
                "repository": f"{bundle.repository.owner}/{bundle.repository.name}",
                "branch": bundle.branch,
                "has_jira": bundle.jira_issue is not None,
                "has_pr": bundle.pr_data is not None,
                "comment_count": len(bundle.comments),
                "complexity_score": self._calculate_complexity(bundle)
            }
            
            return analysis
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