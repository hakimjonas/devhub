"""Platform-agnostic SDK for DevHub with equal first-class support for all platforms.

This module provides a unified interface for all development platforms (GitHub, GitLab, Jira, etc.)
ensuring no platform receives preferential treatment in the core architecture.

Classes:
    Platform: Platform identification and capabilities
    PlatformSDK: Main SDK with unified platform interface
    GitLabSDK: Comprehensive GitLab integration
    GitHubAdvancedSDK: Enhanced GitHub integration with Projects support
    PlatformRegistry: Registry for managing platform implementations
"""

import json
from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from typing import Any
from typing import Protocol
from typing import runtime_checkable

from returns.result import Failure
from returns.result import Result
from returns.result import Success

from devhub.connection_pool import HTTPPool
from devhub.vault import SecureVault


class PlatformType(Enum):
    """Supported platform types."""

    VERSION_CONTROL = "version_control"
    ISSUE_TRACKING = "issue_tracking"
    PROJECT_MANAGEMENT = "project_management"
    CI_CD = "ci_cd"
    COMMUNICATION = "communication"
    DOCUMENTATION = "documentation"


class AuthMethod(Enum):
    """Authentication methods."""

    TOKEN = "token"  # noqa: S105
    OAUTH = "oauth"
    SSH_KEY = "ssh_key"
    USERNAME_PASSWORD = "username_password"  # noqa: S105
    API_KEY = "api_key"


@dataclass(frozen=True, slots=True)
class PlatformCapability:
    """Platform capability definition."""

    name: str
    description: str
    required_auth: AuthMethod
    optional_params: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class Platform:
    """Platform identification and capabilities."""

    name: str
    display_name: str
    platform_type: PlatformType
    base_url: str
    capabilities: tuple[PlatformCapability, ...] = field(default_factory=tuple)
    supported_auth_methods: tuple[AuthMethod, ...] = field(default_factory=tuple)

    def supports_capability(self, capability_name: str) -> bool:
        """Check if platform supports a specific capability."""
        return any(cap.name == capability_name for cap in self.capabilities)

    def supports_auth_method(self, auth_method: AuthMethod) -> bool:
        """Check if platform supports an authentication method."""
        return auth_method in self.supported_auth_methods


@runtime_checkable
class PlatformImplementation(Protocol):
    """Protocol for platform implementations."""

    platform: Platform

    async def authenticate(self, credentials: dict[str, Any]) -> Result[None, str]:
        """Authenticate with the platform."""
        ...

    async def test_connection(self) -> Result[dict[str, Any], str]:
        """Test platform connectivity."""
        ...

    async def get_user_info(self) -> Result[dict[str, Any], str]:
        """Get current user information."""
        ...


@runtime_checkable
class RepositoryOperations(Protocol):
    """Protocol for repository operations."""

    async def get_repository(self, owner: str, name: str) -> Result[dict[str, Any], str]:
        """Get repository information."""
        ...

    async def list_pull_requests(self, owner: str, name: str, state: str = "open") -> Result[list[dict[str, Any]], str]:
        """List pull requests."""
        ...

    async def get_pull_request(self, owner: str, name: str, number: int) -> Result[dict[str, Any], str]:
        """Get specific pull request."""
        ...

    async def create_pull_request(
        self, owner: str, name: str, **kwargs: str | float | bool | None
    ) -> Result[dict[str, Any], str]:
        """Create a new pull request."""
        ...


@runtime_checkable
class IssueOperations(Protocol):
    """Protocol for issue operations."""

    async def get_issue(self, project_key: str, issue_key: str) -> Result[dict[str, Any], str]:
        """Get issue information."""
        ...

    async def list_issues(
        self, project_key: str, **filters: str | float | bool | None
    ) -> Result[list[dict[str, Any]], str]:
        """List issues with filters."""
        ...

    async def create_issue(self, project_key: str, **kwargs: str | float | bool | None) -> Result[dict[str, Any], str]:
        """Create a new issue."""
        ...

    async def update_issue(
        self, project_key: str, issue_key: str, **kwargs: str | float | bool | None
    ) -> Result[dict[str, Any], str]:
        """Update an existing issue."""
        ...


@runtime_checkable
class ProjectOperations(Protocol):
    """Protocol for project management operations."""

    async def get_project(self, project_id: str) -> Result[dict[str, Any], str]:
        """Get project information."""
        ...

    async def list_projects(self, **filters: str | float | bool | None) -> Result[list[dict[str, Any]], str]:
        """List projects."""
        ...

    async def get_project_items(self, project_id: str) -> Result[list[dict[str, Any]], str]:
        """Get project items/cards."""
        ...


class GitLabSDK:
    """Comprehensive GitLab SDK with full feature support."""

    def __init__(self, base_url: str = "https://gitlab.com") -> None:
        """Initialize GitLab SDK."""
        self.platform = Platform(
            name="gitlab",
            display_name="GitLab",
            platform_type=PlatformType.VERSION_CONTROL,
            base_url=base_url,
            capabilities=(
                PlatformCapability("repositories", "Repository management", AuthMethod.TOKEN),
                PlatformCapability("merge_requests", "Merge request operations", AuthMethod.TOKEN),
                PlatformCapability("issues", "Issue tracking", AuthMethod.TOKEN),
                PlatformCapability("ci_cd", "CI/CD pipelines", AuthMethod.TOKEN),
                PlatformCapability("wiki", "Wiki management", AuthMethod.TOKEN),
                PlatformCapability("snippets", "Code snippets", AuthMethod.TOKEN),
                PlatformCapability("releases", "Release management", AuthMethod.TOKEN),
            ),
            supported_auth_methods=(AuthMethod.TOKEN, AuthMethod.OAUTH),
        )
        self._http_pool: HTTPPool | None = None
        self._authenticated = False
        self._token: str | None = None

    async def authenticate(self, credentials: dict[str, Any]) -> Result[None, str]:
        """Authenticate with GitLab."""
        try:
            token = credentials.get("token")
            if not token:
                return Failure("GitLab token required")

            self._token = token
            self._http_pool = HTTPPool()

            # Test authentication
            test_result = await self.test_connection()
            if isinstance(test_result, Success):
                self._authenticated = True
                return Success(None)
            return Failure(test_result.failure())

        except (OSError, ValueError, RuntimeError) as e:
            return Failure(f"GitLab authentication failed: {e}")

    async def test_connection(self) -> Result[dict[str, Any], str]:
        """Test GitLab connectivity."""
        if not self._http_pool or not self._token:
            return Failure("Not authenticated")

        try:
            async with self._http_pool.get_session("gitlab") as session:
                result = await session.get(
                    f"{self.platform.base_url}/api/v4/user", headers={"Authorization": f"Bearer {self._token}"}
                )
        except (OSError, ValueError, RuntimeError) as e:
            return Failure(f"GitLab connection test failed: {e}")
        else:
            if isinstance(result, Failure):
                return Failure(result.failure())

            response = result.unwrap()
            return (
                Success(response.json_data or {})
                if response.is_success
                else Failure(f"GitLab API error: {response.status_code}")
            )

    async def get_user_info(self) -> Result[dict[str, Any], str]:
        """Get current GitLab user information."""
        return await self.test_connection()

    async def get_project(self, project_id: str) -> Result[dict[str, Any], str]:
        """Get GitLab project information."""
        if not self._authenticated or not self._http_pool:
            return Failure("Not authenticated" if not self._authenticated else "HTTP pool not initialized")

        try:
            async with self._http_pool.get_session("gitlab") as session:
                result = await session.get(
                    f"{self.platform.base_url}/api/v4/projects/{project_id}",
                    headers={"Authorization": f"Bearer {self._token}"},
                )
        except (OSError, ValueError, KeyError) as e:
            return Failure(f"Failed to get GitLab project: {e}")
        else:
            if isinstance(result, Failure):
                return Failure(result.failure())

            response = result.unwrap()
            return (
                Success(response.json_data or {})
                if response.is_success
                else Failure(f"GitLab API error: {response.status_code}")
            )

    async def list_merge_requests(self, project_id: str, state: str = "opened") -> Result[list[dict[str, Any]], str]:
        """List GitLab merge requests."""
        if not self._authenticated or not self._http_pool:
            return Failure("Not authenticated")

        try:
            async with self._http_pool.get_session("gitlab") as session:
                result = await session.get(
                    f"{self.platform.base_url}/api/v4/projects/{project_id}/merge_requests",
                    params={"state": state},
                    headers={"Authorization": f"Bearer {self._token}"},
                )
        except (OSError, ValueError, KeyError) as e:
            return Failure(f"Failed to list GitLab merge requests: {e}")
        else:
            if isinstance(result, Failure):
                return Failure(result.failure())

            response = result.unwrap()
            return (
                Success(response.json_data or [])
                if response.is_success
                else Failure(f"GitLab API error: {response.status_code}")
            )

    async def get_merge_request(self, project_id: str, merge_request_iid: int) -> Result[dict[str, Any], str]:
        """Get specific GitLab merge request."""
        if not self._authenticated or not self._http_pool:
            return Failure("Not authenticated" if not self._authenticated else "HTTP pool not initialized")

        try:
            async with self._http_pool.get_session("gitlab") as session:
                result = await session.get(
                    f"{self.platform.base_url}/api/v4/projects/{project_id}/merge_requests/{merge_request_iid}",
                    headers={"Authorization": f"Bearer {self._token}"},
                )
        except (OSError, ValueError, KeyError) as e:
            return Failure(f"Failed to get GitLab merge request: {e}")
        else:
            if isinstance(result, Failure):
                return Failure(result.failure())

            response = result.unwrap()
            return (
                Success(response.json_data or {})
                if response.is_success
                else Failure(f"GitLab API error: {response.status_code}")
            )

    async def list_issues(
        self, project_id: str, **filters: str | float | bool | None
    ) -> Result[list[dict[str, Any]], str]:
        """List GitLab issues."""
        if not self._authenticated or not self._http_pool:
            return Failure("Not authenticated" if not self._authenticated else "HTTP pool not initialized")

        # Convert filters to string values for API compatibility
        str_filters = {k: str(v) if v is not None else "" for k, v in filters.items()}

        try:
            async with self._http_pool.get_session("gitlab") as session:
                result = await session.get(
                    f"{self.platform.base_url}/api/v4/projects/{project_id}/issues",
                    params=str_filters,
                    headers={"Authorization": f"Bearer {self._token}"},
                )
        except (OSError, ValueError, KeyError) as e:
            return Failure(f"Failed to list GitLab issues: {e}")
        else:
            if isinstance(result, Failure):
                return Failure(result.failure())

            response = result.unwrap()
            return (
                Success(response.json_data or [])
                if response.is_success
                else Failure(f"GitLab API error: {response.status_code}")
            )

    async def get_pipeline_status(self, project_id: str, ref: str = "main") -> Result[dict[str, Any], str]:
        """Get GitLab CI/CD pipeline status."""
        if not self._authenticated or not self._http_pool:
            return Failure("Not authenticated" if not self._authenticated else "HTTP pool not initialized")

        try:
            async with self._http_pool.get_session("gitlab") as session:
                result = await session.get(
                    f"{self.platform.base_url}/api/v4/projects/{project_id}/pipelines",
                    params={"ref": ref, "per_page": "1"},
                    headers={"Authorization": f"Bearer {self._token}"},
                )
        except (OSError, ValueError, KeyError) as e:
            return Failure(f"Failed to get GitLab pipeline status: {e}")
        else:
            if isinstance(result, Failure):
                return Failure(result.failure())

            response = result.unwrap()
            return (
                Failure(f"GitLab API error: {response.status_code}")
                if not response.is_success
                else Success((response.json_data or [])[0] if response.json_data else {"status": "no_pipelines"})
            )


class GitHubAdvancedSDK:
    """Enhanced GitHub SDK with full Projects and advanced features support."""

    def __init__(self, base_url: str = "https://api.github.com") -> None:
        """Initialize enhanced GitHub SDK."""
        self.platform = Platform(
            name="github",
            display_name="GitHub",
            platform_type=PlatformType.VERSION_CONTROL,
            base_url=base_url,
            capabilities=(
                PlatformCapability("repositories", "Repository management", AuthMethod.TOKEN),
                PlatformCapability("pull_requests", "Pull request operations", AuthMethod.TOKEN),
                PlatformCapability("issues", "Issue tracking", AuthMethod.TOKEN),
                PlatformCapability("projects", "Project boards (V1 & V2)", AuthMethod.TOKEN),
                PlatformCapability("actions", "GitHub Actions", AuthMethod.TOKEN),
                PlatformCapability("packages", "Package registry", AuthMethod.TOKEN),
                PlatformCapability("security", "Security features", AuthMethod.TOKEN),
                PlatformCapability("codespaces", "GitHub Codespaces", AuthMethod.TOKEN),
                PlatformCapability("copilot", "GitHub Copilot integration", AuthMethod.TOKEN),
            ),
            supported_auth_methods=(AuthMethod.TOKEN, AuthMethod.OAUTH),
        )
        self._http_pool: HTTPPool | None = None
        self._authenticated = False
        self._token: str | None = None

    async def authenticate(self, credentials: dict[str, Any]) -> Result[None, str]:
        """Authenticate with GitHub."""
        try:
            token = credentials.get("token")
            if not token:
                return Failure("GitHub token required")

            self._token = token
            self._http_pool = HTTPPool()

            # Test authentication
            test_result = await self.test_connection()
            if isinstance(test_result, Success):
                self._authenticated = True
                return Success(None)
            return Failure(test_result.failure())

        except (OSError, ValueError, RuntimeError) as e:
            return Failure(f"GitHub authentication failed: {e}")

    async def test_connection(self) -> Result[dict[str, Any], str]:
        """Test GitHub connectivity."""
        if not self._http_pool or not self._token:
            return Failure("Not authenticated")

        try:
            async with self._http_pool.get_session("github") as session:
                result = await session.get(
                    f"{self.platform.base_url}/user", headers={"Authorization": f"token {self._token}"}
                )
        except (OSError, ValueError, RuntimeError) as e:
            return Failure(f"GitHub connection test failed: {e}")
        else:
            if isinstance(result, Failure):
                return Failure(result.failure())

            response = result.unwrap()
            return (
                Success(response.json_data or {})
                if response.is_success
                else Failure(f"GitHub API error: {response.status_code}")
            )

    async def get_user_info(self) -> Result[dict[str, Any], str]:
        """Get current GitHub user information."""
        return await self.test_connection()

    # GitHub Projects V2 (GraphQL API)
    async def list_projects_v2(self, owner: str, owner_type: str = "user") -> Result[list[dict[str, Any]], str]:
        """List GitHub Projects V2."""
        if not self._authenticated or not self._http_pool:
            return Failure("Not authenticated" if not self._authenticated else "HTTP pool not initialized")

        query = """
        query($owner: String!, $first: Int!) {
          %s(login: $owner) {
            projectsV2(first: $first) {
              nodes {
                id
                title
                shortDescription
                public
                closed
                createdAt
                updatedAt
                url
              }
            }
          }
        }
        """ % ("user" if owner_type == "user" else "organization")

        try:
            async with self._http_pool.get_session("github") as session:
                result = await session.post(
                    "https://api.github.com/graphql",
                    headers={"Authorization": f"token {self._token}"},
                    data=json.dumps({"query": query, "variables": {"owner": owner, "first": 100}}),
                )
        except (OSError, ValueError, KeyError) as e:
            return Failure(f"Failed to list GitHub Projects V2: {e}")
        else:
            if isinstance(result, Failure):
                return Failure(result.failure())

            response = result.unwrap()
            return (
                Failure(f"GitHub GraphQL error: {response.status_code}")
                if not (response.is_success and response.json_data)
                else Success(
                    response.json_data.get("data", {}).get(owner_type, {}).get("projectsV2", {}).get("nodes", [])
                )
            )

    async def get_project_v2_items(self, project_id: str) -> Result[list[dict[str, Any]], str]:
        """Get GitHub Project V2 items."""
        if not self._authenticated or not self._http_pool:
            return Failure("Not authenticated" if not self._authenticated else "HTTP pool not initialized")

        query = """
        query($projectId: ID!, $first: Int!) {
          node(id: $projectId) {
            ... on ProjectV2 {
              items(first: $first) {
                nodes {
                  id
                  type
                  createdAt
                  updatedAt
                  content {
                    ... on Issue {
                      id
                      title
                      state
                      number
                      url
                    }
                    ... on PullRequest {
                      id
                      title
                      state
                      number
                      url
                    }
                  }
                }
              }
            }
          }
        }
        """

        try:
            async with self._http_pool.get_session("github") as session:
                result = await session.post(
                    "https://api.github.com/graphql",
                    headers={"Authorization": f"token {self._token}"},
                    data=json.dumps({"query": query, "variables": {"projectId": project_id, "first": 100}}),
                )
        except (OSError, ValueError, KeyError) as e:
            return Failure(f"Failed to get GitHub Project V2 items: {e}")
        else:
            if isinstance(result, Failure):
                return Failure(result.failure())

            response = result.unwrap()
            return (
                Failure(f"GitHub GraphQL error: {response.status_code}")
                if not (response.is_success and response.json_data)
                else Success(response.json_data.get("data", {}).get("node", {}).get("items", {}).get("nodes", []))
            )

    async def get_repository_insights(self, owner: str, repo: str) -> Result[dict[str, Any], str]:
        """Get comprehensive repository insights."""
        if not self._authenticated:
            return Failure("Not authenticated")

        insights = {}

        # Get basic repo info
        repo_result = await self._get_repository(owner, repo)
        if isinstance(repo_result, Success):
            insights["repository"] = repo_result.unwrap()

        # Get contributor stats
        contributors_result = await self._get_contributors(owner, repo)
        if isinstance(contributors_result, Success):
            insights["contributors"] = contributors_result.unwrap()

        # Get recent releases
        releases_result = await self._get_releases(owner, repo)
        if isinstance(releases_result, Success):
            insights["releases"] = releases_result.unwrap()

        # Get actions status
        actions_result = await self._get_actions_status(owner, repo)
        if isinstance(actions_result, Success):
            insights["actions"] = actions_result.unwrap()

        return Success(insights)

    async def _get_repository(self, owner: str, repo: str) -> Result[dict[str, Any], str]:
        """Get repository information."""
        if not self._http_pool:
            return Failure("HTTP pool not initialized")
        async with self._http_pool.get_session("github") as session:
            result = await session.get(
                f"{self.platform.base_url}/repos/{owner}/{repo}", headers={"Authorization": f"token {self._token}"}
            )
            if isinstance(result, Success):
                response = result.unwrap()
                return Success(response.json_data or {})
            return Failure(result.failure())

    async def _get_contributors(self, owner: str, repo: str) -> Result[list[dict[str, Any]], str]:
        """Get repository contributors."""
        if not self._http_pool:
            return Failure("HTTP pool not initialized")
        async with self._http_pool.get_session("github") as session:
            result = await session.get(
                f"{self.platform.base_url}/repos/{owner}/{repo}/contributors",
                headers={"Authorization": f"token {self._token}"},
            )
            if isinstance(result, Success):
                response = result.unwrap()
                return Success(response.json_data or [])
            return Failure(result.failure())

    async def _get_releases(self, owner: str, repo: str) -> Result[list[dict[str, Any]], str]:
        """Get repository releases."""
        if not self._http_pool:
            return Failure("HTTP pool not initialized")
        async with self._http_pool.get_session("github") as session:
            result = await session.get(
                f"{self.platform.base_url}/repos/{owner}/{repo}/releases",
                params={"per_page": "10"},
                headers={"Authorization": f"token {self._token}"},
            )
            if isinstance(result, Success):
                response = result.unwrap()
                return Success(response.json_data or [])
            return Failure(result.failure())

    async def _get_actions_status(self, owner: str, repo: str) -> Result[dict[str, Any], str]:
        """Get GitHub Actions status."""
        if not self._http_pool:
            return Failure("HTTP pool not initialized")
        async with self._http_pool.get_session("github") as session:
            result = await session.get(
                f"{self.platform.base_url}/repos/{owner}/{repo}/actions/runs",
                params={"per_page": "1"},
                headers={"Authorization": f"token {self._token}"},
            )
            if isinstance(result, Success):
                response = result.unwrap()
                runs = response.json_data.get("workflow_runs", []) if response.json_data else []
                return Success(runs[0] if runs else {"status": "no_runs"})
            return Failure(result.failure())


class PlatformRegistry:
    """Registry for managing platform implementations."""

    def __init__(self) -> None:
        """Initialize platform registry."""
        self._platforms: dict[str, PlatformImplementation] = {}
        self._vault: SecureVault | None = None

    def register_platform(self, platform_impl: PlatformImplementation) -> Result[None, str]:
        """Register a platform implementation."""
        try:
            self._platforms[platform_impl.platform.name] = platform_impl
            return Success(None)

        except (ValueError, TypeError) as e:
            return Failure(f"Failed to register platform: {e}")

    def get_platform(self, name: str) -> PlatformImplementation | None:
        """Get platform implementation by name."""
        return self._platforms.get(name)

    def list_platforms(self) -> list[Platform]:
        """List all registered platforms."""
        return [impl.platform for impl in self._platforms.values()]

    async def authenticate_platform(
        self, platform_name: str, credentials: dict[str, Any] | None = None
    ) -> Result[None, str]:
        """Authenticate with a platform using stored or provided credentials."""
        platform_impl = self.get_platform(platform_name)
        if not platform_impl:
            return Failure(f"Platform '{platform_name}' not registered")

        # If no credentials provided, try to get from vault
        if credentials is None and self._vault:
            vault_result = await self._vault.get_credential(f"{platform_name}_credentials")
            if isinstance(vault_result, Success):
                credentials = json.loads(vault_result.unwrap())
            else:
                return Failure(f"No credentials found for {platform_name}")

        if not credentials:
            return Failure(f"No credentials provided for {platform_name}")

        return await platform_impl.authenticate(credentials)

    def set_vault(self, vault: SecureVault) -> None:
        """Set credential vault for automatic authentication."""
        self._vault = vault


class PlatformSDK:
    """Main platform-agnostic SDK with unified interface."""

    def __init__(self) -> None:
        """Initialize platform SDK."""
        self._registry = PlatformRegistry()
        self._initialize_default_platforms()

    def _initialize_default_platforms(self) -> None:
        """Initialize default platform implementations."""
        # Register GitLab
        gitlab_sdk = GitLabSDK()
        self._registry.register_platform(gitlab_sdk)

        # Register enhanced GitHub
        github_sdk = GitHubAdvancedSDK()
        self._registry.register_platform(github_sdk)

    @property
    def gitlab(self) -> GitLabSDK:
        """Get GitLab SDK instance."""
        gitlab_impl = self._registry.get_platform("gitlab")
        if not isinstance(gitlab_impl, GitLabSDK):
            msg = "GitLab platform not properly registered"
            raise TypeError(msg)
        return gitlab_impl

    @property
    def github(self) -> GitHubAdvancedSDK:
        """Get GitHub SDK instance."""
        github_impl = self._registry.get_platform("github")
        if not isinstance(github_impl, GitHubAdvancedSDK):
            msg = "GitHub platform not properly registered"
            raise TypeError(msg)
        return github_impl

    @property
    def registry(self) -> PlatformRegistry:
        """Get platform registry."""
        return self._registry

    async def authenticate_all(self, credentials_map: dict[str, dict[str, Any]]) -> Result[dict[str, bool], str]:
        """Authenticate with multiple platforms."""
        results = {}

        for platform_name, credentials in credentials_map.items():
            auth_result = await self._registry.authenticate_platform(platform_name, credentials)
            results[platform_name] = isinstance(auth_result, Success)

        return Success(results)

    def list_available_platforms(self) -> list[Platform]:
        """List all available platforms."""
        return self._registry.list_platforms()

    def get_platform_capabilities(self, platform_name: str) -> list[PlatformCapability]:
        """Get capabilities for a specific platform."""
        platform_impl = self._registry.get_platform(platform_name)
        if platform_impl:
            return list(platform_impl.platform.capabilities)
        return []


# Global platform SDK instance
_global_platform_sdk: PlatformSDK | None = None


def get_platform_sdk() -> PlatformSDK:
    """Get the global platform SDK instance."""
    if _global_platform_sdk is None:
        globals()["_global_platform_sdk"] = PlatformSDK()
    return _global_platform_sdk
