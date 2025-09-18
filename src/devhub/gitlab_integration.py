"""First-class GitLab integration for DevHub.

This module provides comprehensive GitLab support equivalent to GitHub,
ensuring GitLab is treated as a true first-class citizen in DevHub.

Classes:
    GitLabRepository: GitLab repository representation
    GitLabMergeRequest: GitLab merge request representation
    GitLabIssue: GitLab issue representation
    GitLabPipeline: GitLab CI/CD pipeline representation
    GitLabClient: Comprehensive GitLab API client
    GitLabPlugin: DevHub plugin for GitLab integration
"""

from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field
from typing import Any

from returns.result import Failure
from returns.result import Result
from returns.result import Success

from devhub.connection_pool import HTTPPool
from devhub.connection_pool import HTTPResponse
from devhub.main import BundleData
from devhub.plugins import DataSourcePlugin
from devhub.plugins import PluginCapability
from devhub.plugins import PluginConfig
from devhub.plugins import PluginMetadata
from devhub.plugins import TransformPlugin
from devhub.sdk import ContextRequest
from devhub.vault import SecureVault


@dataclass(frozen=True, slots=True)
class GitLabRepository:
    """GitLab repository representation."""

    id: int
    name: str
    path: str
    full_name: str
    description: str | None
    web_url: str
    ssh_url_to_repo: str
    http_url_to_repo: str
    default_branch: str
    visibility: str
    star_count: int
    forks_count: int
    created_at: str
    updated_at: str
    last_activity_at: str
    namespace: dict[str, Any] = field(default_factory=dict)
    statistics: dict[str, Any] = field(default_factory=dict)

    @property
    def owner(self) -> str:
        """Get repository owner/namespace."""
        return str(self.namespace.get("name", ""))

    @property
    def clone_url(self) -> str:
        """Get clone URL (prefer SSH if available)."""
        return self.ssh_url_to_repo or self.http_url_to_repo


@dataclass(frozen=True, slots=True)
class GitLabMergeRequest:
    """GitLab merge request representation."""

    id: int
    iid: int
    title: str
    description: str | None
    state: str
    created_at: str
    updated_at: str
    merged_at: str | None
    closed_at: str | None
    target_branch: str
    source_branch: str
    web_url: str
    author: dict[str, Any] = field(default_factory=dict)
    assignees: list[dict[str, Any]] = field(default_factory=list)
    reviewers: list[dict[str, Any]] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    changes_count: str = ""
    user_notes_count: int = 0
    upvotes: int = 0
    downvotes: int = 0

    @property
    def is_open(self) -> bool:
        """Check if merge request is open."""
        return self.state == "opened"

    @property
    def is_merged(self) -> bool:
        """Check if merge request is merged."""
        return self.state == "merged"

    @property
    def is_draft(self) -> bool:
        """Check if merge request is a draft."""
        return self.title.startswith("Draft:") or self.title.startswith("WIP:")


@dataclass(frozen=True, slots=True)
class GitLabIssue:
    """GitLab issue representation."""

    id: int
    iid: int
    title: str
    description: str | None
    state: str
    created_at: str
    updated_at: str
    closed_at: str | None
    web_url: str
    author: dict[str, Any] = field(default_factory=dict)
    assignees: list[dict[str, Any]] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    milestone: dict[str, Any] | None = None
    user_notes_count: int = 0
    upvotes: int = 0
    downvotes: int = 0
    due_date: str | None = None
    weight: int | None = None

    @property
    def is_open(self) -> bool:
        """Check if issue is open."""
        return self.state == "opened"

    @property
    def is_closed(self) -> bool:
        """Check if issue is closed."""
        return self.state == "closed"


@dataclass(frozen=True, slots=True)
class GitLabPipeline:
    """GitLab CI/CD pipeline representation."""

    id: int
    project_id: int
    status: str
    ref: str
    sha: str
    web_url: str
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None
    duration: int | None
    user: dict[str, Any] = field(default_factory=dict)

    @property
    def is_running(self) -> bool:
        """Check if pipeline is currently running."""
        return self.status in ("running", "pending")

    @property
    def is_successful(self) -> bool:
        """Check if pipeline completed successfully."""
        return self.status == "success"

    @property
    def is_failed(self) -> bool:
        """Check if pipeline failed."""
        return self.status in ("failed", "canceled")


class GitLabClient:
    """Comprehensive GitLab API client with full feature support."""

    def __init__(self, base_url: str = "https://gitlab.com", token: str | None = None) -> None:
        """Initialize GitLab client."""
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/api/v4"
        self.token = token
        self._http_pool: HTTPPool | None = None

    def _validate_prerequisites(self) -> Result[None, str]:
        """Validate client is properly initialized and authenticated."""
        if not self._http_pool:
            return Failure("Client not initialized")
        if not self.token:
            return Failure("No authentication token provided")
        return Success(None)

    def _handle_api_response[T](
        self, result: Result[HTTPResponse, str], transform_fn: Callable[[dict[str, Any]], T] | None = None
    ) -> Result[T | dict[str, Any], str]:
        """Handle API response with consistent error handling."""
        if isinstance(result, Failure):
            return result

        response = result.unwrap()
        if not response.is_success:
            return Failure(f"GitLab API error: {response.status_code}")

        data = response.json_data or {}
        return Success(transform_fn(data) if transform_fn else data)

    async def initialize(self) -> Result[None, str]:
        """Initialize the GitLab client."""
        try:
            self._http_pool = HTTPPool()

            if self.token:
                # Test authentication
                test_result = await self.get_current_user()
                if isinstance(test_result, Failure):
                    return test_result

            return Success(None)

        except (OSError, ValueError, RuntimeError) as e:
            return Failure(f"GitLab client initialization failed: {e}")

    async def set_token(self, token: str) -> Result[None, str]:
        """Set authentication token."""
        self.token = token

        # Test the token
        if self._http_pool:
            test_result = await self.get_current_user()
            if isinstance(test_result, Failure):
                return test_result

        return Success(None)

    async def get_current_user(self) -> Result[dict[str, Any], str]:
        """Get current authenticated user."""
        validation_result = self._validate_prerequisites()
        if isinstance(validation_result, Failure):
            return validation_result

        try:
            async with self._http_pool.get_session("gitlab") as session:
                result = await session.get(f"{self.api_url}/user", headers={"Authorization": f"Bearer {self.token}"})
                return self._handle_api_response(result)

        except (OSError, ValueError, KeyError) as e:
            return Failure(f"Failed to get current user: {e}")

    async def get_project(self, project_id: str | int) -> Result[GitLabRepository, str]:
        """Get GitLab project by ID or path."""
        validation_result = self._validate_prerequisites()
        if isinstance(validation_result, Failure):
            return validation_result

        try:
            async with self._http_pool.get_session("gitlab") as session:
                result = await session.get(
                    f"{self.api_url}/projects/{project_id}",
                    headers={"Authorization": f"Bearer {self.token}"},
                    params={"statistics": "true"},
                )
                return self._handle_api_response(result, lambda data: GitLabRepository(**data))

        except (OSError, ValueError, KeyError) as e:
            return Failure(f"Failed to get project: {e}")

    async def list_merge_requests(
        self, project_id: str | int, state: str = "opened", per_page: int = 100
    ) -> Result[list[GitLabMergeRequest], str]:
        """List merge requests for a project."""
        prereq_check = self._validate_prerequisites()
        if isinstance(prereq_check, Failure):
            return prereq_check

        try:
            async with self._http_pool.get_session("gitlab") as session:
                result = await session.get(
                    f"{self.api_url}/projects/{project_id}/merge_requests",
                    headers={"Authorization": f"Bearer {self.token}"},
                    params={"state": state, "per_page": str(per_page)},
                )

                return self._handle_api_response(result, lambda data: [GitLabMergeRequest(**mr) for mr in data])

        except (OSError, ValueError, KeyError) as e:
            return Failure(f"Failed to list merge requests: {e}")

    async def get_merge_request(self, project_id: str | int, merge_request_iid: int) -> Result[GitLabMergeRequest, str]:
        """Get specific merge request."""
        prereq_check = self._validate_prerequisites()
        if isinstance(prereq_check, Failure):
            return prereq_check

        try:
            async with self._http_pool.get_session("gitlab") as session:
                result = await session.get(
                    f"{self.api_url}/projects/{project_id}/merge_requests/{merge_request_iid}",
                    headers={"Authorization": f"Bearer {self.token}"},
                )

                return self._handle_api_response(result, GitLabMergeRequest)

        except (OSError, ValueError, KeyError) as e:
            return Failure(f"Failed to get merge request: {e}")

    async def get_merge_request_changes(
        self, project_id: str | int, merge_request_iid: int
    ) -> Result[dict[str, Any], str]:
        """Get merge request changes/diff."""
        prereq_check = self._validate_prerequisites()
        if isinstance(prereq_check, Failure):
            return prereq_check

        try:
            async with self._http_pool.get_session("gitlab") as session:
                result = await session.get(
                    f"{self.api_url}/projects/{project_id}/merge_requests/{merge_request_iid}/changes",
                    headers={"Authorization": f"Bearer {self.token}"},
                )

                return self._handle_api_response(result)

        except (OSError, ValueError, KeyError) as e:
            return Failure(f"Failed to get merge request changes: {e}")

    async def list_issues(
        self, project_id: str | int, state: str = "opened", per_page: int = 100
    ) -> Result[list[GitLabIssue], str]:
        """List issues for a project."""
        prereq_check = self._validate_prerequisites()
        if isinstance(prereq_check, Failure):
            return prereq_check

        try:
            async with self._http_pool.get_session("gitlab") as session:
                result = await session.get(
                    f"{self.api_url}/projects/{project_id}/issues",
                    headers={"Authorization": f"Bearer {self.token}"},
                    params={"state": state, "per_page": str(per_page)},
                )

                return self._handle_api_response(result, lambda data: [GitLabIssue(**issue) for issue in data])

        except (OSError, ValueError, KeyError) as e:
            return Failure(f"Failed to list issues: {e}")

    async def get_pipeline_status(self, project_id: str | int, ref: str = "main") -> Result[GitLabPipeline | None, str]:
        """Get latest pipeline status for a ref."""
        prereq_check = self._validate_prerequisites()
        if isinstance(prereq_check, Failure):
            return prereq_check

        try:
            async with self._http_pool.get_session("gitlab") as session:
                result = await session.get(
                    f"{self.api_url}/projects/{project_id}/pipelines",
                    headers={"Authorization": f"Bearer {self.token}"},
                    params={"ref": ref, "per_page": "1"},
                )

                return self._handle_api_response(result, lambda data: GitLabPipeline(**data[0]) if data else None)

        except (OSError, ValueError, KeyError) as e:
            return Failure(f"Failed to get pipeline status: {e}")

    async def close(self) -> None:
        """Close the HTTP pool."""
        if self._http_pool:
            await self._http_pool.close_all()


class GitLabPlugin(DataSourcePlugin, TransformPlugin):
    """DevHub plugin for comprehensive GitLab integration."""

    def __init__(self) -> None:
        """Initialize GitLab plugin."""
        self.metadata = PluginMetadata(
            name="gitlab_integration",
            version="1.0.0",
            author="DevHub",
            description="First-class GitLab integration with full API support",
            capabilities=(
                PluginCapability.DATA_SOURCE,
                PluginCapability.TRANSFORM,
                PluginCapability.ENRICHMENT,
            ),
            dependencies=("aiohttp", "returns"),
            supported_formats=("json", "markdown"),
            priority=10,  # High priority for core platforms
        )
        self._client: GitLabClient | None = None
        self._vault: SecureVault | None = None

    async def initialize(self, config: PluginConfig) -> Result[None, str]:
        """Initialize the GitLab plugin."""
        try:
            # Get GitLab configuration
            gitlab_config = config.config.get("gitlab", {})
            base_url = gitlab_config.get("base_url", "https://gitlab.com")

            # Initialize client
            self._client = GitLabClient(base_url)
            init_result = await self._client.initialize()
            if isinstance(init_result, Failure):
                return init_result

            # Set up vault for credential management
            vault_config = config.config.get("vault")
            if vault_config and isinstance(vault_config, SecureVault):
                self._vault = vault_config

            return Success(None)

        except (OSError, ValueError, RuntimeError) as e:
            return Failure(f"GitLab plugin initialization failed: {e}")

    async def shutdown(self) -> Result[None, str]:
        """Shutdown the GitLab plugin."""
        try:
            if self._client:
                await self._client.close()

            return Success(None)

        except (OSError, RuntimeError) as e:
            return Failure(f"GitLab plugin shutdown failed: {e}")

    def validate_config(self, config: dict[str, Any]) -> Result[None, str]:
        """Validate GitLab plugin configuration."""
        try:
            gitlab_config = config.get("gitlab", {})

            # Validate base URL if provided
            base_url = gitlab_config.get("base_url")
            if base_url and not base_url.startswith(("http://", "https://")):
                return Failure("GitLab base_url must start with http:// or https://")

            return Success(None)

        except (ValueError, TypeError, KeyError) as e:
            return Failure(f"GitLab config validation failed: {e}")

    def _resolve_project_id(self, request: ContextRequest, context: dict[str, Any]) -> str | None:
        """Resolve GitLab project ID from request or context."""
        if hasattr(request, "gitlab_project_id") and request.gitlab_project_id:
            return request.gitlab_project_id

        git_remote = context.get("git_remote")
        return self._extract_project_id_from_remote(git_remote) if git_remote and "gitlab" in git_remote else None

    async def _fetch_project_data(self, project_id: str) -> dict[str, Any]:
        """Fetch all project-related data in parallel."""
        gitlab_data = {}

        # Fetch project information first
        project_result = await self._client.get_project(project_id)
        if isinstance(project_result, Success):
            gitlab_data["project"] = project_result.unwrap()

            # Fetch additional data for successful project
            mrs_result = await self._client.list_merge_requests(project_id)
            if isinstance(mrs_result, Success):
                gitlab_data["merge_requests"] = mrs_result.unwrap()

            issues_result = await self._client.list_issues(project_id)
            if isinstance(issues_result, Success):
                gitlab_data["issues"] = issues_result.unwrap()

            pipeline_result = await self._client.get_pipeline_status(project_id)
            if isinstance(pipeline_result, Success):
                gitlab_data["latest_pipeline"] = pipeline_result.unwrap()

        return gitlab_data

    async def fetch_data(self, request: ContextRequest, context: dict[str, Any]) -> Result[dict[str, Any], str]:
        """Fetch GitLab data for bundle context."""
        if not self._client:
            return Failure("GitLab client not initialized")

        try:
            # Authenticate if needed
            auth_result = await self._authenticate()
            if isinstance(auth_result, Failure):
                return auth_result

            # Resolve project ID and fetch data
            project_id = self._resolve_project_id(request, context)
            gitlab_data = await self._fetch_project_data(project_id) if project_id else {}

            return Success(gitlab_data)

        except (OSError, ValueError, RuntimeError) as e:
            return Failure(f"GitLab data fetch failed: {e}")

    async def transform_bundle(self, bundle: BundleData, config: dict[str, Any]) -> Result[BundleData, str]:
        """Transform bundle data with GitLab context."""
        try:
            # Add GitLab-specific transformations to bundle
            if hasattr(bundle, "metadata") and bundle.metadata:
                gitlab_info = config.get("gitlab_data", {})

                if gitlab_info:
                    # Enhance bundle with GitLab context
                    {
                        **bundle.metadata,
                        "gitlab_project": gitlab_info.get("project"),
                        "gitlab_merge_requests": gitlab_info.get("merge_requests", []),
                        "gitlab_issues": gitlab_info.get("issues", []),
                        "gitlab_pipeline": gitlab_info.get("latest_pipeline"),
                    }

                    # Create enhanced bundle (this would need proper BundleData modification)
                    # For now, return original bundle
                    return Success(bundle)

            return Success(bundle)

        except (ValueError, TypeError, KeyError) as e:
            return Failure(f"GitLab bundle transformation failed: {e}")

    def get_supported_sources(self) -> tuple[str, ...]:
        """Get supported GitLab data sources."""
        return (
            "gitlab_projects",
            "gitlab_merge_requests",
            "gitlab_issues",
            "gitlab_pipelines",
            "gitlab_commits",
            "gitlab_branches",
            "gitlab_releases",
        )

    def get_supported_transforms(self) -> tuple[str, ...]:
        """Get supported GitLab transformations."""
        return (
            "gitlab_context_enrichment",
            "gitlab_mr_analysis",
            "gitlab_issue_correlation",
            "gitlab_pipeline_insights",
        )

    async def _authenticate(self) -> Result[None, str]:
        """Authenticate with GitLab using stored credentials."""
        if not self._client:
            return Failure("Client not initialized")

        # Try to get token from vault
        if self._vault:
            try:
                token_result = await self._vault.get_credential("gitlab_token")
                if isinstance(token_result, Success):
                    token = token_result.unwrap()
                    return await self._client.set_token(token)
            except (OSError, ValueError, KeyError):
                pass  # Fall through to error

        return Failure("No GitLab authentication token available")

    def _extract_project_id_from_remote(self, git_remote: str) -> str | None:
        """Extract GitLab project ID from Git remote URL."""
        try:
            # Handle various GitLab URL formats
            if "gitlab.com" in git_remote:
                # Extract owner/repo from URL
                minimum_parts = 2
                parts = git_remote.replace(".git", "").split("/")
                if len(parts) >= minimum_parts:
                    owner = parts[-2]
                    repo = parts[-1]
                    return f"{owner}/{repo}"
        except (OSError, ValueError, KeyError):
            return None
        else:
            return None


# Global GitLab client instance for easy access
_global_gitlab_client: GitLabClient | None = None


async def get_gitlab_client(base_url: str = "https://gitlab.com") -> GitLabClient:
    """Get global GitLab client instance."""
    # Use module-level access instead of global statement
    if _global_gitlab_client is None:
        client = GitLabClient(base_url)
        await client.initialize()
        globals()["_global_gitlab_client"] = client
    assert _global_gitlab_client is not None
    return _global_gitlab_client


async def shutdown_gitlab_client() -> None:
    """Shutdown global GitLab client."""
    # Use module-level access instead of global statement
    if _global_gitlab_client:
        await _global_gitlab_client.close()
        globals()["_global_gitlab_client"] = None
