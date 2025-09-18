"""Claude Code integration for DevHub - The Perfect Synergy.

This module provides seamless integration between DevHub and Claude Code,
creating a powerful development partnership that amplifies both tools.

Classes:
    ClaudeContext: Rich context bundling for Claude sessions
    ClaudeWorkflow: Workflow automation with Claude
    ClaudeMetrics: Performance tracking for Claude interactions
    ClaudeEnhancer: Main integration orchestrator
"""

import json
import time
from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from pathlib import Path
from typing import Any
from typing import TypedDict

import aiofiles
from returns.result import Failure
from returns.result import Result
from returns.result import Success

from devhub.main import BundleData
from devhub.main import Repository
from devhub.observability import get_global_collector
from devhub.vault import get_global_vault


class ClaudeTaskType(Enum):
    """Types of Claude tasks for tracking."""

    CODE_REVIEW = "code_review"
    DOCUMENTATION = "documentation"
    DEBUGGING = "debugging"
    ARCHITECTURE = "architecture"
    TESTING = "testing"
    REFACTORING = "refactoring"
    PLANNING = "planning"
    ANALYSIS = "analysis"


class ClaudeContextKwargs(TypedDict, total=False):
    """Type-safe kwargs for get_enhanced_context method."""

    pr_number: int | None
    mr_iid: int | None
    max_tokens: int
    error_description: str
    relevant_files: list[str] | None


@dataclass(frozen=True, slots=True)
class ClaudeContext:
    """Rich context bundle optimized for Claude Code sessions."""

    # Core project information
    project_name: str
    platform: str  # "github", "gitlab", "local", etc.
    repository_url: str | None = None

    # Codebase context
    total_files: int = 0
    total_lines: int = 0
    primary_languages: list[str] = field(default_factory=list)
    architecture_summary: str = ""

    # Recent activity
    recent_commits: list[dict[str, Any]] = field(default_factory=list)
    open_pull_requests: list[dict[str, Any]] = field(default_factory=list)
    open_issues: list[dict[str, Any]] = field(default_factory=list)

    # Current state
    current_branch: str = ""
    working_tree_status: str = ""
    ci_cd_status: dict[str, Any] = field(default_factory=dict)

    # Dependencies and tech stack
    dependencies: dict[str, list[str]] = field(default_factory=dict)
    frameworks: list[str] = field(default_factory=list)

    # Documentation
    readme_summary: str = ""
    documentation_coverage: float = 0.0

    # Quality metrics
    test_coverage: float = 0.0
    code_quality_score: float = 0.0
    security_issues: list[dict[str, Any]] = field(default_factory=list)

    # Context metadata
    generated_at: float = field(default_factory=time.time)
    token_estimate: int = 0
    context_completeness: float = 0.0

    def to_claude_prompt(self) -> str:
        """Convert context to Claude-optimized prompt."""
        prompt_parts = [
            f"# Project: {self.project_name}",
            f"Platform: {self.platform}",
            "",
            "## Project Overview",
            f"- Files: {self.total_files:,} ({self.total_lines:,} lines)",
            f"- Languages: {', '.join(self.primary_languages)}",
            f"- Current branch: {self.current_branch}",
            "",
        ]

        if self.architecture_summary:
            prompt_parts.extend(
                [
                    "## Architecture",
                    self.architecture_summary,
                    "",
                ]
            )

        if self.open_pull_requests:
            prompt_parts.extend(
                [
                    f"## Active Pull/Merge Requests ({len(self.open_pull_requests)})",
                    *[
                        f"- #{pr.get('number', pr.get('iid', '?'))}: {pr.get('title', 'Untitled')}"
                        for pr in self.open_pull_requests[:5]
                    ],
                    "",
                ]
            )

        if self.open_issues:
            prompt_parts.extend(
                [
                    f"## Open Issues ({len(self.open_issues)})",
                    *[
                        f"- #{issue.get('number', issue.get('iid', '?'))}: {issue.get('title', 'Untitled')}"
                        for issue in self.open_issues[:5]
                    ],
                    "",
                ]
            )

        if self.ci_cd_status:
            status = self.ci_cd_status.get("status", "unknown")
            prompt_parts.extend(
                [
                    f"## CI/CD Status: {status}",
                    "",
                ]
            )

        if self.frameworks:
            prompt_parts.extend(
                [
                    f"## Tech Stack: {', '.join(self.frameworks)}",
                    "",
                ]
            )

        prompt_parts.extend(
            [
                "## Quality Metrics",
                f"- Test coverage: {self.test_coverage:.1f}%",
                f"- Code quality: {self.code_quality_score:.1f}/10",
                f"- Documentation: {self.documentation_coverage:.1f}%",
                "",
            ]
        )

        if self.recent_commits:
            prompt_parts.extend(
                [
                    "## Recent Activity",
                    *[f"- {commit.get('message', 'No message')[:60]}..." for commit in self.recent_commits[:3]],
                    "",
                ]
            )

        return "\n".join(prompt_parts)


@dataclass(frozen=True, slots=True)
class ClaudeMetrics:
    """Metrics for Claude Code interactions."""

    session_id: str
    task_type: ClaudeTaskType
    start_time: float
    end_time: float | None = None

    # Context metrics
    context_size_tokens: int = 0
    context_completeness: float = 0.0

    # Performance metrics
    response_time_seconds: float = 0.0
    suggestions_count: int = 0
    code_changes_count: int = 0

    # Quality metrics
    user_satisfaction: float | None = None  # 1-5 scale
    follow_up_questions: int = 0
    corrections_needed: int = 0

    # Success indicators
    task_completed: bool = False
    solution_applied: bool = False

    @property
    def duration_seconds(self) -> float:
        """Calculate session duration."""
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time

    @property
    def effectiveness_score(self) -> float:
        """Calculate effectiveness score (0-1)."""
        base_score = 0.5

        if self.task_completed:
            base_score += 0.3

        if self.solution_applied:
            base_score += 0.2

        if self.user_satisfaction:
            base_score += (self.user_satisfaction - 3) * 0.1  # Adjust based on satisfaction

        # Penalize for many corrections
        base_score -= min(self.corrections_needed * 0.05, 0.2)

        return max(0.0, min(1.0, base_score))


class ClaudeWorkflow:
    """Automated workflows for Claude Code integration."""

    def __init__(self) -> None:
        """Initialize Claude workflow automation."""
        # Note: SDK integration would be implemented here
        self._metrics_collector = get_global_collector()
        self._vault = get_global_vault()

    async def prepare_code_review_context(
        self, pr_number: int | None = None, mr_iid: int | None = None, max_tokens: int = 50000
    ) -> Result[ClaudeContext, str]:
        """Prepare comprehensive context for Claude code review."""
        try:
            # Note: This would gather bundle data from the actual SDK
            # For demonstration, we'll create a mock bundle
            mock_bundle = BundleData(
                repository=Repository(owner="user", name="demo-project"),
                metadata={"current_branch": "main", "recent_commits": []},
            )
            bundle = mock_bundle

            # Detect platform and get platform-specific data
            platform_data = {}

            if pr_number:  # GitHub
                platform_data = await self._get_github_pr_context(pr_number)
            elif mr_iid:  # GitLab
                platform_data = await self._get_gitlab_mr_context(mr_iid)

            # Build Claude context
            context = self.build_claude_context(bundle, platform_data, max_tokens)

            return Success(context)

        except (OSError, ValueError, RuntimeError) as e:
            return Failure(f"Failed to prepare code review context: {e}")

    async def prepare_debugging_context(
        self, error_description: str, relevant_files: list[Path] | None = None
    ) -> Result[ClaudeContext, str]:
        """Prepare context for debugging assistance."""
        try:
            # Note: Mock implementation for demonstration
            mock_bundle = BundleData(
                repository=Repository(owner="user", name="demo-project"),
                metadata={"current_branch": "main", "recent_commits": []},
            )
            bundle = mock_bundle

            # Add error context
            debug_data = {
                "error_description": error_description,
                "relevant_files": [str(f) for f in (relevant_files or [])],
                "recent_changes": bundle.metadata.get("recent_commits", [])[:5],
            }

            context = self.build_claude_context(bundle, debug_data, max_tokens=30000)

            return Success(context)

        except (OSError, ValueError, RuntimeError) as e:
            return Failure(f"Failed to prepare debugging context: {e}")

    async def prepare_architecture_context(self) -> Result[ClaudeContext, str]:
        """Prepare context for architecture discussions."""
        try:
            # Note: Mock implementation for demonstration
            mock_bundle = BundleData(
                repository=Repository(owner="user", name="demo-project"),
                metadata={
                    "documentation": {"coverage": 95.0},
                    "files": {},
                    "dependencies": {"python": ["fastapi", "aiohttp", "returns"]},
                    "current_branch": "main",
                    "recent_commits": [],
                    "clone_url": "https://github.com/user/demo-project",
                },
            )
            bundle = mock_bundle

            # Focus on high-level structure
            arch_data = {
                "module_structure": bundle.metadata.get("dependencies", {}),
                "documentation": bundle.metadata.get("documentation", {}),
                "configuration": bundle.metadata.get("config_files", {}),
            }

            context = self.build_claude_context(bundle, arch_data, max_tokens=40000)

            return Success(context)

        except (OSError, ValueError, RuntimeError) as e:
            return Failure(f"Failed to prepare architecture context: {e}")

    def build_claude_context(
        self, bundle: BundleData, platform_data: dict[str, Any], max_tokens: int = 50000
    ) -> ClaudeContext:
        """Build optimized Claude context from bundle and platform data."""
        # Extract key information
        git_info = bundle.metadata or {}
        repo_info = bundle.repository or None

        # Calculate metrics
        total_files = len(bundle.metadata.get("files", {})) if bundle.metadata.get("files") else 0
        total_lines = sum(
            len(file_data.get("content", "").split("\n"))
            for file_data in (bundle.metadata.get("files", {}) or {}).values()
        )

        # Determine platform
        platform = "local"
        repo_url = None
        if repo_info:
            clone_url = bundle.metadata.get("clone_url", "")
            if "github" in clone_url:
                platform = "github"
            elif "gitlab" in clone_url:
                platform = "gitlab"
            repo_url = clone_url

        # Extract languages from file extensions
        languages = []
        files_dict = bundle.metadata.get("files", {})
        if files_dict:
            extensions = set()
            for file_path in files_dict:
                ext = Path(file_path).suffix.lower()
                if ext:
                    extensions.add(ext)

            # Map common extensions to languages
            lang_map = {
                ".py": "Python",
                ".js": "JavaScript",
                ".ts": "TypeScript",
                ".java": "Java",
                ".cpp": "C++",
                ".c": "C",
                ".cs": "C#",
                ".go": "Go",
                ".rs": "Rust",
                ".rb": "Ruby",
                ".php": "PHP",
                ".html": "HTML",
                ".css": "CSS",
                ".scss": "SCSS",
                ".json": "JSON",
                ".yaml": "YAML",
                ".yml": "YAML",
                ".md": "Markdown",
                ".sql": "SQL",
                ".sh": "Shell",
            }

            languages = [lang_map.get(ext, ext[1:].upper()) for ext in extensions if ext in lang_map]

        return ClaudeContext(
            project_name=repo_info.name if repo_info else Path.cwd().name,
            platform=platform,
            repository_url=repo_url,
            total_files=total_files,
            total_lines=total_lines,
            primary_languages=languages[:5],  # Top 5 languages
            current_branch=git_info.get("current_branch", ""),
            open_pull_requests=platform_data.get("pull_requests", []),
            open_issues=platform_data.get("issues", []),
            recent_commits=git_info.get("recent_commits", [])[:5],
            ci_cd_status=platform_data.get("ci_status", {}),
            dependencies=bundle.metadata.get("dependencies", {}),
            token_estimate=min(max_tokens, total_lines // 10),  # Rough estimate
            context_completeness=0.8 if platform_data else 0.6,
        )

    async def _get_github_pr_context(self, _pr_number: int) -> dict[str, Any]:
        """Get GitHub PR context."""
        try:
            # This would be implemented with actual GitHub API calls
            return {
                "pull_requests": [],  # Would fetch actual PRs
                "issues": [],  # Would fetch linked issues
                "ci_status": {},  # Would fetch CI status
            }
        except (OSError, ValueError, RuntimeError):
            # Fall back to empty data on errors
            pass
        return {}

    async def _get_gitlab_mr_context(self, _mr_iid: int) -> dict[str, Any]:
        """Get GitLab MR context."""
        try:
            # This would be implemented with actual GitLab API calls
            return {
                "merge_requests": [],  # Would fetch actual MRs
                "issues": [],  # Would fetch linked issues
                "ci_status": {},  # Would fetch pipeline status
            }
        except (OSError, ValueError, RuntimeError):
            # Fall back to empty data on errors
            pass
        return {}


class ClaudeEnhancer:
    """Main Claude Code integration orchestrator."""

    def __init__(self) -> None:
        """Initialize Claude enhancer."""
        self._workflow = ClaudeWorkflow()
        self._metrics_collector = get_global_collector()
        self._active_sessions: dict[str, ClaudeMetrics] = {}

    def start_claude_session(self, task_type: ClaudeTaskType, session_id: str | None = None) -> str:
        """Start a tracked Claude session."""
        if not session_id:
            session_id = f"claude_{int(time.time())}"

        metrics = ClaudeMetrics(
            session_id=session_id,
            task_type=task_type,
            start_time=time.time(),
        )

        self._active_sessions[session_id] = metrics

        # Record session start
        self._metrics_collector.record_metric("claude_sessions_started", 1.0, {"task_type": task_type.value})

        return session_id

    def end_claude_session(
        self,
        session_id: str,
        task_completed: bool = False,
        solution_applied: bool = False,
        user_satisfaction: float | None = None,
    ) -> Result[ClaudeMetrics, str]:
        """End and finalize a Claude session."""
        if session_id not in self._active_sessions:
            return Failure(f"Session {session_id} not found")

        metrics = self._active_sessions[session_id]

        # Update final metrics
        final_metrics = ClaudeMetrics(
            session_id=metrics.session_id,
            task_type=metrics.task_type,
            start_time=metrics.start_time,
            end_time=time.time(),
            context_size_tokens=metrics.context_size_tokens,
            context_completeness=metrics.context_completeness,
            response_time_seconds=metrics.response_time_seconds,
            suggestions_count=metrics.suggestions_count,
            code_changes_count=metrics.code_changes_count,
            follow_up_questions=metrics.follow_up_questions,
            corrections_needed=metrics.corrections_needed,
            task_completed=task_completed,
            solution_applied=solution_applied,
            user_satisfaction=user_satisfaction,
        )

        # Record session metrics
        self._metrics_collector.record_metric(
            "claude_session_duration", final_metrics.duration_seconds, {"task_type": metrics.task_type.value}
        )

        self._metrics_collector.record_metric(
            "claude_effectiveness_score", final_metrics.effectiveness_score, {"task_type": metrics.task_type.value}
        )

        # Clean up active session
        del self._active_sessions[session_id]

        return Success(final_metrics)

    async def get_enhanced_context(
        self, task_type: ClaudeTaskType, **kwargs: ClaudeContextKwargs
    ) -> Result[ClaudeContext, str]:
        """Get enhanced context for Claude based on task type."""
        if task_type == ClaudeTaskType.CODE_REVIEW:
            pr_number = kwargs.get("pr_number")
            mr_iid = kwargs.get("mr_iid")
            max_tokens = kwargs.get("max_tokens", 50000)
            return await self._workflow.prepare_code_review_context(pr_number, mr_iid, max_tokens)
        if task_type == ClaudeTaskType.DEBUGGING:
            error_description = kwargs.get("error_description", "")
            relevant_files = kwargs.get("relevant_files")
            return await self._workflow.prepare_debugging_context(error_description, relevant_files)
        if task_type == ClaudeTaskType.ARCHITECTURE:
            return await self._workflow.prepare_architecture_context()
        # Note: Mock implementation for demonstration
        mock_bundle = BundleData(
            repository=Repository(owner="user", name="demo-project"),
            metadata={},
        )
        bundle = mock_bundle
        context = self._workflow.build_claude_context(bundle, {})
        return Success(context)

    def get_session_analytics(self) -> dict[str, Any]:
        """Get analytics for Claude sessions."""
        active_count = len(self._active_sessions)

        # Group by task type
        task_counts: dict[str, int] = {}
        for session in self._active_sessions.values():
            task_type = session.task_type.value
            task_counts[task_type] = task_counts.get(task_type, 0) + 1

        return {
            "active_sessions": active_count,
            "sessions_by_task": task_counts,
            "total_sessions_today": active_count,  # Would track historical data
        }

    async def export_session_data(self, output_file: Path) -> Result[None, str]:
        """Export Claude session data for analysis."""
        try:
            analytics = self.get_session_analytics()

            export_data = {
                "timestamp": time.time(),
                "analytics": analytics,
                "active_sessions": [
                    {
                        "session_id": session.session_id,
                        "task_type": session.task_type.value,
                        "duration": session.duration_seconds,
                        "context_size": session.context_size_tokens,
                    }
                    for session in self._active_sessions.values()
                ],
            }

            async with aiofiles.open(output_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(export_data, indent=2))

            return Success(None)

        except (OSError, ValueError, RuntimeError) as e:
            return Failure(f"Failed to export session data: {e}")


# Global Claude enhancer instance - using class-based singleton
class _ClaudeEnhancerSingleton:
    """Singleton wrapper for ClaudeEnhancer."""

    _instance: ClaudeEnhancer | None = None

    @classmethod
    def get_instance(cls) -> ClaudeEnhancer:
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = ClaudeEnhancer()
        return cls._instance


def get_claude_enhancer() -> ClaudeEnhancer:
    """Get the global Claude enhancer instance."""
    return _ClaudeEnhancerSingleton.get_instance()


# Convenience functions for common Claude workflows
async def claude_code_review_context(pr_number: int | None = None) -> Result[str, str]:
    """Get Claude-optimized context for code review."""
    enhancer = get_claude_enhancer()
    context_result = await enhancer.get_enhanced_context(ClaudeTaskType.CODE_REVIEW, pr_number=pr_number)

    if isinstance(context_result, Success):
        context = context_result.unwrap()
        return Success(context.to_claude_prompt())
    return Failure(context_result.failure())


async def claude_debugging_context(error_description: str) -> Result[str, str]:
    """Get Claude-optimized context for debugging."""
    enhancer = get_claude_enhancer()
    context_result = await enhancer.get_enhanced_context(ClaudeTaskType.DEBUGGING, error_description=error_description)

    if isinstance(context_result, Success):
        context = context_result.unwrap()
        return Success(context.to_claude_prompt())
    return Failure(context_result.failure())


async def claude_architecture_context() -> Result[str, str]:
    """Get Claude-optimized context for architecture discussions."""
    enhancer = get_claude_enhancer()
    context_result = await enhancer.get_enhanced_context(ClaudeTaskType.ARCHITECTURE)

    if isinstance(context_result, Success):
        context = context_result.unwrap()
        return Success(context.to_claude_prompt())
    return Failure(context_result.failure())
