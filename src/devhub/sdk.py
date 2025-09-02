"""DevHub Programmatic SDK for agent development.

This module provides a clean, type-safe Python SDK for interacting with DevHub
functionality programmatically. It maintains DevHub's functional programming
principles while providing convenient APIs for AI agents and custom tools.
"""

import argparse
import asyncio
import json
import time
import types
from collections.abc import AsyncIterator
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any
from typing import cast

from returns.result import Failure
from returns.result import Result
from returns.result import Success

from devhub.config import DevHubConfig
from devhub.config import load_config_with_environment
from devhub.main import BundleConfig
from devhub.main import BundleData
from devhub.main import JiraIssue
from devhub.main import Repository
from devhub.main import ReviewComment
from devhub.main import _gather_bundle_data
from devhub.main import fetch_jira_issue
from devhub.main import fetch_pr_details
from devhub.main import fetch_pr_diff
from devhub.main import fetch_unresolved_comments
from devhub.main import get_current_branch
from devhub.main import get_jira_credentials
from devhub.main import get_jira_credentials_from_config
from devhub.main import get_repository_info
from devhub.main import resolve_jira_key_with_config
from devhub.main import resolve_pr_number


@dataclass(frozen=True, slots=True)
class SDKConfig:
    """Immutable SDK configuration."""

    workspace_path: Path = field(default_factory=Path.cwd)
    organization: str | None = None
    cache_enabled: bool = True
    cache_ttl_seconds: int = 300
    timeout_seconds: int = 30


@dataclass(frozen=True, slots=True)
class ContextRequest:
    """Immutable context request configuration."""

    jira_key: str | None = None
    pr_number: int | None = None
    branch: str | None = None
    include_jira: bool = True
    include_pr: bool = True
    include_diff: bool = True
    include_comments: bool = True
    comment_limit: int = 20
    metadata_only: bool = False


@dataclass(frozen=True, slots=True)
class StreamUpdate:
    """Immutable stream update notification."""

    update_type: str  # 'pr_updated', 'comment_added', 'branch_changed'
    data: dict[str, Any]
    timestamp: str


class DevHubClient:
    """Main SDK client for programmatic DevHub access."""

    def __init__(self, config: SDKConfig | None = None) -> None:
        """Initialize DevHub client with configuration."""
        self._config = config or SDKConfig()
        self._devhub_config: DevHubConfig | None = None
        self._cache: dict[str, tuple[float, Any]] = {}

    async def initialize(self) -> Result[None, str]:
        """Initialize the client and load DevHub configuration."""
        try:
            config_result = load_config_with_environment()
            if isinstance(config_result, Success):
                self._devhub_config = config_result.unwrap()
            else:
                self._devhub_config = DevHubConfig()

            return Success(None)
        except (ValueError, TypeError, OSError) as e:
            return Failure(f"Failed to initialize DevHub client: {e}")

    async def get_bundle_context(self, request: ContextRequest | None = None) -> Result[BundleData, str]:
        """Get comprehensive bundle context."""
        init_result = await self._ensure_initialized()
        if isinstance(init_result, Failure):
            return init_result

        req = request or ContextRequest()

        # Check cache first
        cached_result = self._check_cache("bundle", req)
        if cached_result:
            return cached_result

        try:
            return await self._build_bundle_context(req)
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            return Failure(f"Failed to get bundle context: {e}")

    async def _ensure_initialized(self) -> Result[None, str]:
        """Ensure DevHub client is initialized."""
        if not self._devhub_config:
            return await self.initialize()
        return Success(None)

    def _check_cache(self, cache_type: str, request: ContextRequest) -> Result[BundleData, str] | None:
        """Check for cached result."""
        if self._config.cache_enabled:
            cached = self._get_cached_result(cache_type, request)
            if cached:
                return Success(cast("BundleData", cached))
        return None

    async def _build_bundle_context(self, req: ContextRequest) -> Result[BundleData, str]:
        """Build bundle context from request."""
        repo_branch_result = self._get_repo_and_branch(req)
        if isinstance(repo_branch_result, Failure):
            return repo_branch_result
        repo, branch = repo_branch_result.unwrap()

        jira_key, pr_number = self._resolve_identifiers(req, branch, repo)
        bundle_config = self._create_bundle_config(req)

        result = self._gather_data(req, bundle_config, repo, branch, jira_key, pr_number)
        if isinstance(result, Failure):
            return result

        return self._process_result(result.unwrap(), repo, branch, req)

    def _get_repo_and_branch(self, req: ContextRequest) -> Result[tuple[Repository, str], str]:
        """Get repository info and branch."""
        repo_result = get_repository_info()
        if isinstance(repo_result, Failure):
            return repo_result
        repo = repo_result.unwrap()

        branch = req.branch
        if not branch:
            branch_result = get_current_branch()
            if isinstance(branch_result, Failure):
                return branch_result
            branch = branch_result.unwrap()

        return Success((repo, branch))

    def _resolve_identifiers(self, req: ContextRequest, branch: str, repo: Repository) -> tuple[str | None, int | None]:
        """Resolve Jira key and PR number."""
        jira_key = req.jira_key
        if not jira_key and self._devhub_config:
            jira_key = resolve_jira_key_with_config(
                self._devhub_config, branch=branch, org_name=self._config.organization
            )

        pr_number = req.pr_number
        if not pr_number:
            pr_result = resolve_pr_number(repo, None, branch, jira_key)
            if isinstance(pr_result, Success):
                pr_number = pr_result.unwrap()

        return jira_key, pr_number

    def _create_bundle_config(self, req: ContextRequest) -> BundleConfig:
        """Create bundle configuration."""
        return BundleConfig(
            include_jira=req.include_jira,
            include_pr=req.include_pr,
            include_diff=req.include_diff,
            include_comments=req.include_comments,
            limit=req.comment_limit,
            organization=self._config.organization,
        )

    def _gather_data(
        self,
        req: ContextRequest,
        bundle_config: BundleConfig,
        repo: Repository,
        branch: str,
        jira_key: str | None,
        pr_number: int | None,
    ) -> Result[str, str]:
        """Gather bundle data."""
        args = argparse.Namespace(metadata_only=req.metadata_only, format="json")
        devhub_config = self._devhub_config or DevHubConfig()

        return _gather_bundle_data(args, bundle_config, repo, branch, jira_key, pr_number, devhub_config)

    def _process_result(
        self, json_result: str, repo: Repository, branch: str, req: ContextRequest
    ) -> Result[BundleData, str]:
        """Process the JSON result into BundleData."""
        try:
            json_data = json.loads(json_result)
            bundle_data = self._json_to_bundle_data(json_data, repo, branch)

            if self._config.cache_enabled:
                self._cache_result("bundle", req, bundle_data)

            return Success(bundle_data)
        except json.JSONDecodeError as e:
            return Failure(f"Failed to process bundle data: Invalid JSON - {e}")
        except (ValueError, TypeError, KeyError) as e:
            return Failure(f"Failed to process bundle data: {e}")

    async def get_jira_issue(self, jira_key: str) -> Result[JiraIssue, str]:
        """Get specific Jira issue details."""
        if not self._devhub_config:
            init_result = await self.initialize()
            if isinstance(init_result, Failure):
                return init_result

        try:
            # Get credentials
            devhub_config = self._devhub_config or DevHubConfig()
            credentials = get_jira_credentials_from_config(devhub_config, self._config.organization)
            if not credentials:
                credentials = get_jira_credentials()

            if not credentials:
                return Failure("Jira credentials not configured")

            # Fetch issue
            return fetch_jira_issue(credentials, jira_key)

        except (ValueError, TypeError, KeyError) as e:
            return Failure(f"Failed to get Jira issue: {e}")

    async def get_pr_details(self, pr_number: int, include_diff: bool = True) -> Result[dict[str, Any], str]:
        """Get GitHub PR details."""
        try:
            # Get repository info
            repo_result = get_repository_info()
            if isinstance(repo_result, Failure):
                return repo_result
            repo = repo_result.unwrap()

            # Fetch PR details
            pr_result = fetch_pr_details(repo, pr_number)
            if isinstance(pr_result, Failure):
                return pr_result

            pr_data = pr_result.unwrap()

            # Add diff if requested
            if include_diff:
                diff_result = fetch_pr_diff(pr_number)
                if isinstance(diff_result, Success):
                    pr_data["diff"] = diff_result.unwrap()

            return Success(pr_data)

        except (ValueError, TypeError, KeyError) as e:
            return Failure(f"Failed to get PR details: {e}")

    async def get_pr_comments(self, pr_number: int, limit: int = 20) -> Result[tuple[ReviewComment, ...], str]:
        """Get unresolved PR review comments."""
        try:
            # Get repository info
            repo_result = get_repository_info()
            if isinstance(repo_result, Failure):
                return repo_result
            repo = repo_result.unwrap()

            # Fetch comments
            return fetch_unresolved_comments(repo, pr_number, limit)

        except (ValueError, TypeError, KeyError) as e:
            return Failure(f"Failed to get PR comments: {e}")

    async def get_current_branch_context(
        self,
        include_diff: bool = True,
        include_comments: bool = True,
        comment_limit: int = 20,
    ) -> Result[BundleData, str]:
        """Get context for current branch with auto-detection."""
        return await self.get_bundle_context(
            ContextRequest(
                include_diff=include_diff,
                include_comments=include_comments,
                comment_limit=comment_limit,
            )
        )

    async def stream_pr_updates(self, pr_number: int) -> AsyncIterator[StreamUpdate]:
        """Stream real-time updates for a PR."""
        # This would implement polling or webhook-based streaming
        # For now, we'll implement a simple polling mechanism
        time.time()

        while True:
            try:
                # Get current PR state
                pr_result = await self.get_pr_details(pr_number)
                if isinstance(pr_result, Success):
                    pr_data = pr_result.unwrap()

                    # Check for updates (simplified - would need more sophisticated tracking)
                    update_time = pr_data.get("updated_at", "")
                    if update_time:
                        # Would parse timestamp and compare
                        yield StreamUpdate(
                            update_type="pr_updated",
                            data=pr_data,
                            timestamp=update_time,
                        )

                # Wait before next poll
                await asyncio.sleep(30)  # Poll every 30 seconds

            except (ValueError, TypeError, KeyError):
                # Handle errors gracefully
                await asyncio.sleep(60)  # Wait longer on error

    async def execute_cli_command(
        self,
        command: list[str],
        capture_output: bool = True,
    ) -> Result[str, str]:
        """Execute DevHub CLI command programmatically."""
        ret: Result[str, str]
        try:
            full_command = ["uv", "run", "devhub", *command]

            if capture_output:
                process = await asyncio.create_subprocess_exec(
                    *full_command,
                    cwd=self._config.workspace_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                process = await asyncio.create_subprocess_exec(
                    *full_command,
                    cwd=self._config.workspace_path,
                )

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self._config.timeout_seconds)

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Command failed"
                ret = Failure(f"CLI command failed: {error_msg}")
            else:
                output = stdout.decode() if stdout else ""
                ret = Success(output)

        except TimeoutError:
            ret = Failure("CLI command timed out")
        except KeyboardInterrupt:
            ret = Failure("Command interrupted by user")
        except (OSError, ValueError) as e:
            ret = Failure(f"CLI command error: {e}")

        return ret

    def _json_to_bundle_data(
        self,
        json_data: dict[str, Any],
        repo: Repository,
        branch: str,
    ) -> BundleData:
        """Convert JSON data to BundleData object."""
        # Extract Jira issue
        jira_issue = None
        if jira_data := json_data.get("jira"):
            jira_issue = JiraIssue(
                key=jira_data["key"],
                summary=jira_data.get("summary"),
                description=jira_data.get("description"),
                raw_data=jira_data.get("raw_data", {}),
            )

        # Extract comments
        comments = tuple(
            ReviewComment(
                id=comment["id"],
                body=comment["body"],
                path=comment.get("path"),
                author=comment.get("author"),
                created_at=comment.get("created_at"),
                diff_hunk=comment.get("diff_hunk"),
                resolved=comment.get("resolved", False),
            )
            for comment in json_data.get("comments", [])
        )

        return BundleData(
            jira_issue=jira_issue,
            pr_data=json_data.get("pull_request"),
            pr_diff=json_data.get("diff"),
            comments=comments,
            repository=repo,
            branch=branch,
            metadata=json_data.get("metadata", {}),
        )

    def _get_cached_result(self, cache_type: str, request: object) -> object | None:
        """Get cached result if available and not expired."""
        if not self._config.cache_enabled:
            return None

        cache_key = f"{cache_type}_{hash(str(request))}"

        if cache_key in self._cache:
            timestamp, data = self._cache[cache_key]
            if time.time() - timestamp < self._config.cache_ttl_seconds:
                return cast("object", data)
            del self._cache[cache_key]

        return None

    def _cache_result(self, cache_type: str, request: object, data: object) -> None:
        """Cache result with timestamp."""
        if not self._config.cache_enabled:
            return

        cache_key = f"{cache_type}_{hash(str(request))}"
        self._cache[cache_key] = (time.time(), data)


class DevHubAsyncClient:
    """Async-first DevHub client for high-performance applications."""

    def __init__(self, config: SDKConfig | None = None) -> None:
        """Initialize async DevHub client."""
        self._client = DevHubClient(config)

    async def __aenter__(self) -> "DevHubAsyncClient":
        """Async context manager entry."""
        await self._client.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        # Cleanup if needed

    async def get_bundle_context(self, request: ContextRequest | None = None) -> Result[BundleData, str]:
        """Get bundle context asynchronously."""
        return await self._client.get_bundle_context(request)

    async def get_multiple_contexts(
        self,
        requests: list[ContextRequest],
    ) -> list[Result[BundleData, str]]:
        """Get multiple bundle contexts concurrently."""
        tasks = [self._client.get_bundle_context(req) for req in requests]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        # Filter out exceptions and return only Results
        return [r for r in results if isinstance(r, (Success, Failure))]

    async def stream_updates(self, pr_number: int) -> AsyncIterator[StreamUpdate]:
        """Stream updates asynchronously."""
        async for update in self._client.stream_pr_updates(pr_number):
            yield update


# Convenience functions for quick access
async def get_current_context() -> Result[BundleData, str]:
    """Quick function to get current branch context."""
    async with DevHubAsyncClient() as client:
        return await client.get_bundle_context()


async def get_context_for_jira(jira_key: str) -> Result[BundleData, str]:
    """Quick function to get context for specific Jira issue."""
    async with DevHubAsyncClient() as client:
        return await client.get_bundle_context(ContextRequest(jira_key=jira_key))


async def get_context_for_pr(pr_number: int) -> Result[BundleData, str]:
    """Quick function to get context for specific PR."""
    async with DevHubAsyncClient() as client:
        return await client.get_bundle_context(ContextRequest(pr_number=pr_number))


# Export main classes and functions
__all__ = [
    "ContextRequest",
    "DevHubAsyncClient",
    "DevHubClient",
    "SDKConfig",
    "StreamUpdate",
    "get_context_for_jira",
    "get_context_for_pr",
    "get_current_context",
]
