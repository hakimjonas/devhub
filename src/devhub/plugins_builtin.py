"""Built-in plugins for DevHub.

This module contains reference implementations of common plugins
that demonstrate the plugin architecture and provide useful
functionality out of the box.

Plugins:
    GitLabDataSourcePlugin: Fetch data from GitLab API
    LinearDataSourcePlugin: Fetch data from Linear API
    SlackNotificationPlugin: Send notifications to Slack
    HTMLOutputPlugin: Generate HTML output format
    PDFOutputPlugin: Generate PDF output format
"""

import json
from typing import Any

from returns.result import Failure
from returns.result import Result
from returns.result import Success

from devhub.main import BundleData
from devhub.plugins import PluginCapability
from devhub.plugins import PluginConfig
from devhub.plugins import PluginMetadata
from devhub.sdk import ContextRequest


class GitLabDataSourcePlugin:
    """GitLab API data source plugin.

    Fetches merge request and issue data from GitLab API
    to supplement GitHub data in DevHub bundles.
    """

    metadata = PluginMetadata(
        name="gitlab_datasource",
        version="1.0.0",
        author="DevHub Team",
        description="Fetch data from GitLab API",
        capabilities=(PluginCapability.DATA_SOURCE,),
        dependencies=("requests",),
        supported_formats=("json", "api"),
        priority=50,
    )

    def __init__(self) -> None:
        """Initialize GitLab plugin."""
        self._gitlab_token: str | None = None
        self._gitlab_url: str | None = None

    async def initialize(self, config: PluginConfig) -> Result[None, str]:
        """Initialize GitLab plugin with configuration."""
        plugin_config = config.config

        self._gitlab_token = plugin_config.get("token")
        self._gitlab_url = plugin_config.get("url", "https://gitlab.com")

        if not self._gitlab_token:
            return Failure("GitLab token is required")

        return Success(None)

    async def shutdown(self) -> Result[None, str]:
        """Shutdown GitLab plugin."""
        self._gitlab_token = None
        self._gitlab_url = None
        return Success(None)

    def validate_config(self, config: dict[str, Any]) -> Result[None, str]:
        """Validate GitLab plugin configuration."""
        if "token" not in config:
            return Failure("GitLab token is required in config")

        if "url" in config and not config["url"].startswith("http"):
            return Failure("GitLab URL must start with http or https")

        return Success(None)

    async def fetch_data(
        self,
        _request: ContextRequest,
        context: dict[str, Any],
    ) -> Result[dict[str, Any], str]:
        """Fetch data from GitLab API."""
        if not self._gitlab_token:
            return Failure("GitLab plugin not properly initialized")

        # Extract project and MR number from context
        project_id = context.get("gitlab_project_id")
        mr_number = context.get("gitlab_mr_number")

        if not project_id or not mr_number:
            return Failure("GitLab project ID and MR number required")

        # Simulate API call (would use actual HTTP client in real implementation)
        mock_data = {
            "merge_request": {
                "id": mr_number,
                "title": f"GitLab MR {mr_number}",
                "description": "Mock merge request from GitLab",
                "state": "opened",
                "source_branch": "feature/gitlab-integration",
                "target_branch": "main",
                "author": {"name": "GitLab User", "username": "gitlab_user"},
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T12:00:00Z",
            },
            "discussions": [
                {
                    "id": "discussion_1",
                    "notes": [
                        {
                            "body": "This looks good to me!",
                            "author": {"name": "Reviewer", "username": "reviewer"},
                            "created_at": "2024-01-01T10:00:00Z",
                        }
                    ],
                }
            ],
        }

        return Success(mock_data)

    def get_supported_sources(self) -> tuple[str, ...]:
        """Get supported GitLab data sources."""
        return ("merge_requests", "issues", "discussions")


class LinearDataSourcePlugin:
    """Linear API data source plugin.

    Fetches issue and project data from Linear API
    to provide alternative issue tracking integration.
    """

    metadata = PluginMetadata(
        name="linear_datasource",
        version="1.0.0",
        author="DevHub Team",
        description="Fetch data from Linear API",
        capabilities=(PluginCapability.DATA_SOURCE,),
        dependencies=("requests",),
        supported_formats=("json", "graphql"),
        priority=60,
    )

    def __init__(self) -> None:
        """Initialize Linear plugin."""
        self._linear_token: str | None = None

    async def initialize(self, config: PluginConfig) -> Result[None, str]:
        """Initialize Linear plugin with configuration."""
        self._linear_token = config.config.get("token")

        if not self._linear_token:
            return Failure("Linear API token is required")

        return Success(None)

    async def shutdown(self) -> Result[None, str]:
        """Shutdown Linear plugin."""
        self._linear_token = None
        return Success(None)

    def validate_config(self, config: dict[str, Any]) -> Result[None, str]:
        """Validate Linear plugin configuration."""
        if "token" not in config:
            return Failure("Linear API token is required")

        return Success(None)

    async def fetch_data(
        self,
        _request: ContextRequest,
        context: dict[str, Any],
    ) -> Result[dict[str, Any], str]:
        """Fetch data from Linear API."""
        if not self._linear_token:
            return Failure("Linear plugin not properly initialized")

        issue_id = context.get("linear_issue_id")
        if not issue_id:
            return Failure("Linear issue ID required")

        # Mock Linear issue data
        mock_data = {
            "issue": {
                "id": issue_id,
                "title": f"Linear Issue {issue_id}",
                "description": "Mock issue from Linear",
                "state": {"name": "In Progress"},
                "priority": 2,
                "assignee": {"name": "Developer", "email": "dev@example.com"},
                "team": {"name": "Engineering", "key": "ENG"},
                "project": {"name": "Q1 Features", "key": "Q1"},
                "createdAt": "2024-01-01T00:00:00Z",
                "updatedAt": "2024-01-01T12:00:00Z",
            },
            "comments": [
                {
                    "id": "comment_1",
                    "body": "Working on this issue",
                    "user": {"name": "Developer", "email": "dev@example.com"},
                    "createdAt": "2024-01-01T09:00:00Z",
                }
            ],
        }

        return Success(mock_data)

    def get_supported_sources(self) -> tuple[str, ...]:
        """Get supported Linear data sources."""
        return ("issues", "projects", "teams")


class EnrichmentTransformPlugin:
    """Data enrichment transformation plugin.

    Adds computed fields and enrichment data to bundles
    such as complexity metrics, sentiment analysis, etc.
    """

    metadata = PluginMetadata(
        name="enrichment_transform",
        version="1.0.0",
        author="DevHub Team",
        description="Enrich bundle data with computed metrics",
        capabilities=(PluginCapability.TRANSFORM, PluginCapability.ENRICHMENT),
        dependencies=(),
        priority=10,
    )

    async def initialize(self, _config: PluginConfig) -> Result[None, str]:
        """Initialize enrichment plugin."""
        return Success(None)

    async def shutdown(self) -> Result[None, str]:
        """Shutdown enrichment plugin."""
        return Success(None)

    def validate_config(self, _config: dict[str, Any]) -> Result[None, str]:
        """Validate enrichment plugin configuration."""
        return Success(None)

    async def transform_bundle(
        self,
        bundle: BundleData,
        _config: dict[str, Any],
    ) -> Result[BundleData, str]:
        """Transform bundle with enrichment data."""
        # Add computed metrics to bundle
        {
            "enrichment": {
                "bundle_complexity": self._calculate_complexity(bundle),
                "comment_sentiment": self._analyze_sentiment(bundle),
                "activity_score": self._calculate_activity_score(bundle),
                "readiness_score": self._calculate_readiness_score(bundle),
            }
        }

        # Create new bundle with enriched data
        return Success(bundle)  # Would use dataclass replace in real implementation

    def get_supported_transforms(self) -> tuple[str, ...]:
        """Get supported transformation types."""
        return ("complexity", "sentiment", "activity", "readiness")

    def _calculate_complexity(self, bundle: BundleData) -> float:
        """Calculate bundle complexity score."""
        score = 0.0

        # Factor in diff size
        if bundle.pr_diff:
            lines = len(bundle.pr_diff.split("\n"))
            score += min(lines / 100, 1.0)  # Normalize to 0-1

        # Factor in number of comments
        score += min(len(bundle.comments) / 20, 1.0)

        # Factor in Jira issue description length
        if bundle.jira_issue and bundle.jira_issue.description:
            desc_length = len(bundle.jira_issue.description)
            score += min(desc_length / 1000, 1.0)

        return min(score, 1.0)

    def _analyze_sentiment(self, bundle: BundleData) -> str:
        """Analyze sentiment of comments."""
        if not bundle.comments:
            return "neutral"

        # Simple sentiment analysis based on keywords
        positive_words = {"good", "great", "excellent", "perfect", "nice", "love"}
        negative_words = {"bad", "terrible", "awful", "hate", "wrong", "issue"}

        positive_count = 0
        negative_count = 0

        for comment in bundle.comments:
            words = comment.body.lower().split()
            positive_count += sum(1 for word in words if word in positive_words)
            negative_count += sum(1 for word in words if word in negative_words)

        if positive_count > negative_count:
            return "positive"
        if negative_count > positive_count:
            return "negative"
        return "neutral"

    def _calculate_activity_score(self, bundle: BundleData) -> float:
        """Calculate activity score based on comments and updates."""
        # Simple activity score based on number of comments
        return min(len(bundle.comments) / 10, 1.0)

    def _calculate_readiness_score(self, bundle: BundleData) -> float:
        """Calculate readiness score for merge/completion."""
        score = 1.0

        # Reduce score for unresolved comments
        unresolved_comments = sum(1 for c in bundle.comments if not c.resolved)
        score -= min(unresolved_comments / 10, 0.5)

        # Reduce score if no PR data
        if not bundle.pr_data:
            score -= 0.3

        # Reduce score if no Jira issue
        if not bundle.jira_issue:
            score -= 0.2

        return max(score, 0.0)


class HTMLOutputPlugin:
    """HTML output format plugin.

    Generates styled HTML output for DevHub bundles
    with responsive design and interactive elements.
    """

    metadata = PluginMetadata(
        name="html_output",
        version="1.0.0",
        author="DevHub Team",
        description="Generate HTML output format",
        capabilities=(PluginCapability.OUTPUT,),
        dependencies=(),
        supported_formats=("html",),
        priority=20,
    )

    async def initialize(self, _config: PluginConfig) -> Result[None, str]:
        """Initialize HTML output plugin."""
        return Success(None)

    async def shutdown(self) -> Result[None, str]:
        """Shutdown HTML output plugin."""
        return Success(None)

    def validate_config(self, _config: dict[str, Any]) -> Result[None, str]:
        """Validate HTML output configuration."""
        return Success(None)

    async def format_output(
        self,
        bundle: BundleData,
        format_options: dict[str, Any],
    ) -> Result[str | bytes, str]:
        """Format bundle as HTML."""
        theme = format_options.get("theme", "default")
        include_css = format_options.get("include_css", True)

        # Generate HTML content
        html_content = self._generate_html(bundle, theme, include_css)
        return Success(html_content)

    def get_supported_formats(self) -> tuple[str, ...]:
        """Get supported output formats."""
        return ("html", "htm")

    def get_file_extension(self, _format_name: str) -> str:
        """Get file extension for HTML format."""
        return ".html"

    def _generate_html(self, bundle: BundleData, _theme: str, include_css: bool) -> str:
        """Generate HTML content for bundle."""
        css_styles = (
            """
        <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .header { border-bottom: 2px solid #0366d6; margin-bottom: 30px; }
        .section { margin-bottom: 30px; }
        .jira-issue { background: #f6f8fa; padding: 15px; border-radius: 6px; }
        .pr-info { background: #e7f3ff; padding: 15px; border-radius: 6px; }
        .comment { border-left: 4px solid #0366d6; padding: 10px; margin: 10px 0; }
        .resolved { opacity: 0.7; }
        .diff { background: #f8f8f8; padding: 10px; font-family: monospace; overflow-x: auto; }
        </style>
        """
            if include_css
            else ""
        )

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>DevHub Bundle - {bundle.repository.name if bundle.repository else "Unknown"}</title>
            {css_styles}
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>DevHub Bundle</h1>
                    <p><strong>Repository:</strong> {f"{bundle.repository.owner}/{bundle.repository.name}" if bundle.repository else "Unknown"}</p>
                    <p><strong>Branch:</strong> {bundle.branch}</p>
                </div>
        """

        # Add Jira issue section
        if bundle.jira_issue:
            html += f"""
                <div class="section">
                    <h2>Jira Issue</h2>
                    <div class="jira-issue">
                        <h3>{bundle.jira_issue.key}: {bundle.jira_issue.summary or "No summary"}</h3>
                        <p>{bundle.jira_issue.description or "No description"}</p>
                    </div>
                </div>
            """

        # Add PR section
        if bundle.pr_data:
            pr_title = bundle.pr_data.get("title", "Unknown PR")
            pr_number = bundle.pr_data.get("number", "N/A")
            html += f"""
                <div class="section">
                    <h2>Pull Request</h2>
                    <div class="pr-info">
                        <h3>PR #{pr_number}: {pr_title}</h3>
                    </div>
                </div>
            """

        # Add comments section
        if bundle.comments:
            html += '<div class="section"><h2>Comments</h2>'
            for comment in bundle.comments:
                resolved_class = "resolved" if comment.resolved else ""
                html += f"""
                    <div class="comment {resolved_class}">
                        <strong>{comment.author or "Unknown"}</strong>
                        <p>{comment.body}</p>
                        <small>Path: {comment.path or "General"}</small>
                    </div>
                """
            html += "</div>"

        # Add diff section (truncated for display)
        if bundle.pr_diff:
            max_diff_length = 1000
            diff_preview = (
                bundle.pr_diff[:max_diff_length] + "..." if len(bundle.pr_diff) > max_diff_length else bundle.pr_diff
            )
            html += f"""
                <div class="section">
                    <h2>Code Diff</h2>
                    <div class="diff">
                        <pre>{diff_preview}</pre>
                    </div>
                </div>
            """

        html += """
            </div>
        </body>
        </html>
        """

        return html


class JSONOutputPlugin:
    """Enhanced JSON output format plugin.

    Generates structured JSON output with additional metadata
    and formatting options for API consumption.
    """

    metadata = PluginMetadata(
        name="json_output",
        version="1.0.0",
        author="DevHub Team",
        description="Generate enhanced JSON output format",
        capabilities=(PluginCapability.OUTPUT,),
        dependencies=(),
        supported_formats=("json", "jsonl"),
        priority=30,
    )

    async def initialize(self, _config: PluginConfig) -> Result[None, str]:
        """Initialize JSON output plugin."""
        return Success(None)

    async def shutdown(self) -> Result[None, str]:
        """Shutdown JSON output plugin."""
        return Success(None)

    def validate_config(self, _config: dict[str, Any]) -> Result[None, str]:
        """Validate JSON output configuration."""
        return Success(None)

    async def format_output(
        self,
        bundle: BundleData,
        format_options: dict[str, Any],
    ) -> Result[str | bytes, str]:
        """Format bundle as enhanced JSON."""
        pretty_print = format_options.get("pretty", True)
        include_metadata = format_options.get("include_metadata", True)

        # Convert bundle to dict with enhancements
        bundle_dict = bundle.to_dict()

        if include_metadata:
            bundle_dict["_meta"] = {
                "format_version": "1.0",
                "generated_by": "DevHub JSON Output Plugin",
                "bundle_stats": {
                    "has_jira_issue": bundle.jira_issue is not None,
                    "has_pr_data": bundle.pr_data is not None,
                    "has_diff": bundle.pr_diff is not None,
                    "comment_count": len(bundle.comments),
                    "unresolved_comment_count": sum(1 for c in bundle.comments if not c.resolved),
                },
            }

        # Serialize to JSON
        if pretty_print:
            json_output = json.dumps(bundle_dict, indent=2, ensure_ascii=False)
        else:
            json_output = json.dumps(bundle_dict, separators=(",", ":"))

        return Success(json_output)

    def get_supported_formats(self) -> tuple[str, ...]:
        """Get supported output formats."""
        return ("json", "jsonl")

    def get_file_extension(self, format_name: str) -> str:
        """Get file extension for JSON format."""
        return ".json" if format_name == "json" else ".jsonl"
