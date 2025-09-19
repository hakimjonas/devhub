"""Comprehensive tests for Claude integration module.

These tests cover all Claude integration functionality to achieve 90%+ coverage.
"""

import time
from unittest.mock import AsyncMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from returns.result import Failure
from returns.result import Success

from devhub.claude_integration import ClaudeContext
from devhub.claude_integration import ClaudeContextKwargs
from devhub.claude_integration import ClaudeEnhancer
from devhub.claude_integration import ClaudeMetrics
from devhub.claude_integration import ClaudeTaskType
from devhub.claude_integration import ClaudeWorkflow
from devhub.claude_integration import _ClaudeEnhancerSingleton
from devhub.claude_integration import claude_architecture_context
from devhub.claude_integration import claude_code_review_context
from devhub.claude_integration import claude_debugging_context
from devhub.claude_integration import get_claude_enhancer


class TestClaudeTaskType:
    """Test ClaudeTaskType enum."""

    def test_claude_task_type_values(self) -> None:
        """Test ClaudeTaskType enum values."""
        assert ClaudeTaskType.CODE_REVIEW.value == "code_review"
        assert ClaudeTaskType.DOCUMENTATION.value == "documentation"
        assert ClaudeTaskType.DEBUGGING.value == "debugging"
        assert ClaudeTaskType.ARCHITECTURE.value == "architecture"
        assert ClaudeTaskType.TESTING.value == "testing"
        assert ClaudeTaskType.REFACTORING.value == "refactoring"
        assert ClaudeTaskType.PLANNING.value == "planning"
        assert ClaudeTaskType.ANALYSIS.value == "analysis"

    def test_claude_task_type_enum_membership(self) -> None:
        """Test that all expected task types are in the enum."""
        expected_types = {
            "code_review",
            "documentation",
            "debugging",
            "architecture",
            "testing",
            "refactoring",
            "planning",
            "analysis",
        }
        actual_types = {task.value for task in ClaudeTaskType}
        assert actual_types == expected_types


class TestClaudeContext:
    """Test ClaudeContext dataclass."""

    def test_claude_context_creation_minimal(self) -> None:
        """Test creating ClaudeContext with minimal data."""
        context = ClaudeContext(project_name="test-project", platform="github")

        assert context.project_name == "test-project"
        assert context.platform == "github"
        assert context.repository_url is None
        assert context.total_files == 0
        assert context.total_lines == 0
        assert context.primary_languages == []
        assert context.architecture_summary == ""
        assert context.current_branch == ""
        assert context.working_tree_status == ""
        assert isinstance(context.generated_at, float)
        assert context.token_estimate == 0
        assert context.context_completeness == 0.0

    def test_claude_context_creation_full(self) -> None:
        """Test creating ClaudeContext with full data."""
        recent_commits = [
            {"message": "Add new feature", "sha": "abc123"},
            {"message": "Fix bug in parser", "sha": "def456"},
        ]
        open_prs = [{"number": 42, "title": "Feature: Add cool stuff"}]
        open_issues = [{"number": 123, "title": "Bug: Something broken"}]
        ci_cd_status = {"status": "passing", "build_id": "123"}
        dependencies = {"python": ["requests", "fastapi"], "javascript": ["react", "typescript"]}
        frameworks = ["FastAPI", "React", "PostgreSQL"]
        security_issues = [{"type": "vulnerability", "severity": "medium"}]

        context = ClaudeContext(
            project_name="my-awesome-app",
            platform="github",
            repository_url="https://github.com/org/repo",
            total_files=250,
            total_lines=15000,
            primary_languages=["Python", "TypeScript", "SQL"],
            architecture_summary="Microservices architecture with API gateway",
            recent_commits=recent_commits,
            open_pull_requests=open_prs,
            open_issues=open_issues,
            current_branch="feature/cool-stuff",
            working_tree_status="clean",
            ci_cd_status=ci_cd_status,
            dependencies=dependencies,
            frameworks=frameworks,
            readme_summary="A cool app that does awesome things",
            documentation_coverage=85.5,
            test_coverage=92.3,
            code_quality_score=8.7,
            security_issues=security_issues,
            generated_at=1234567890.0,
            token_estimate=5000,
            context_completeness=0.95,
        )

        assert context.project_name == "my-awesome-app"
        assert context.platform == "github"
        assert context.repository_url == "https://github.com/org/repo"
        assert context.total_files == 250
        assert context.total_lines == 15000
        assert context.primary_languages == ["Python", "TypeScript", "SQL"]
        assert context.architecture_summary == "Microservices architecture with API gateway"
        assert context.recent_commits == recent_commits
        assert context.open_pull_requests == open_prs
        assert context.open_issues == open_issues
        assert context.current_branch == "feature/cool-stuff"
        assert context.working_tree_status == "clean"
        assert context.ci_cd_status == ci_cd_status
        assert context.dependencies == dependencies
        assert context.frameworks == frameworks
        assert context.readme_summary == "A cool app that does awesome things"
        assert context.documentation_coverage == 85.5
        assert context.test_coverage == 92.3
        assert context.code_quality_score == 8.7
        assert context.security_issues == security_issues
        assert context.generated_at == 1234567890.0
        assert context.token_estimate == 5000
        assert context.context_completeness == 0.95

    def test_claude_context_immutability(self) -> None:
        """Test that ClaudeContext is immutable."""
        context = ClaudeContext(project_name="test-project", platform="github")

        with pytest.raises(AttributeError):
            context.project_name = "changed"  # type: ignore[misc]

    def test_to_claude_prompt_minimal(self) -> None:
        """Test to_claude_prompt with minimal context."""
        context = ClaudeContext(
            project_name="minimal-project",
            platform="local",
            total_files=5,
            total_lines=100,
            primary_languages=["Python"],
            current_branch="main",
        )

        prompt = context.to_claude_prompt()

        assert "# Project: minimal-project" in prompt
        assert "Platform: local" in prompt
        assert "Files: 5 (100 lines)" in prompt
        assert "Languages: Python" in prompt
        assert "Current branch: main" in prompt
        assert "Test coverage: 0.0%" in prompt
        assert "Code quality: 0.0/10" in prompt
        assert "Documentation: 0.0%" in prompt

    def test_to_claude_prompt_full(self) -> None:
        """Test to_claude_prompt with full context."""
        context = ClaudeContext(
            project_name="full-project",
            platform="github",
            total_files=1000,
            total_lines=50000,
            primary_languages=["Python", "TypeScript"],
            current_branch="feature/awesome",
            architecture_summary="Clean architecture with hexagonal design",
            open_pull_requests=[{"number": 42, "title": "Add feature X"}, {"number": 43, "title": "Fix bug Y"}],
            open_issues=[
                {"number": 100, "title": "Improve performance"},
                {"number": 101, "title": "Add documentation"},
            ],
            ci_cd_status={"status": "passing"},
            frameworks=["FastAPI", "React", "Docker"],
            test_coverage=85.5,
            code_quality_score=9.2,
            documentation_coverage=75.0,
            recent_commits=[
                {"message": "Implement new feature"},
                {"message": "Fix critical bug"},
                {"message": "Update dependencies"},
            ],
        )

        prompt = context.to_claude_prompt()

        # Check project info
        assert "# Project: full-project" in prompt
        assert "Platform: github" in prompt
        assert "Files: 1,000 (50,000 lines)" in prompt
        assert "Languages: Python, TypeScript" in prompt
        assert "Current branch: feature/awesome" in prompt

        # Check architecture
        assert "## Architecture" in prompt
        assert "Clean architecture with hexagonal design" in prompt

        # Check pull requests
        assert "## Active Pull/Merge Requests (2)" in prompt
        assert "- #42: Add feature X" in prompt
        assert "- #43: Fix bug Y" in prompt

        # Check issues
        assert "## Open Issues (2)" in prompt
        assert "- #100: Improve performance" in prompt
        assert "- #101: Add documentation" in prompt

        # Check CI/CD status
        assert "## CI/CD Status: passing" in prompt

        # Check tech stack
        assert "## Tech Stack: FastAPI, React, Docker" in prompt

        # Check quality metrics
        assert "Test coverage: 85.5%" in prompt
        assert "Code quality: 9.2/10" in prompt
        assert "Documentation: 75.0%" in prompt

        # Check recent activity
        assert "## Recent Activity" in prompt
        assert "- Implement new feature..." in prompt
        assert "- Fix critical bug..." in prompt
        assert "- Update dependencies..." in prompt

    def test_to_claude_prompt_long_commit_messages(self) -> None:
        """Test prompt generation with long commit messages."""
        context = ClaudeContext(
            project_name="test-project",
            platform="github",
            recent_commits=[
                {
                    "message": "This is a very long commit message that should be truncated to 60 characters for readability"
                }
            ],
        )

        prompt = context.to_claude_prompt()
        # The actual implementation truncates to 60 characters + "..."
        assert "This is a very long commit message that should be truncated " in prompt


class TestClaudeMetrics:
    """Test ClaudeMetrics dataclass."""

    def test_claude_metrics_creation(self) -> None:
        """Test creating ClaudeMetrics."""
        start_time = time.time()
        end_time = start_time + 5.5

        metrics = ClaudeMetrics(
            session_id="session-123",
            task_type=ClaudeTaskType.CODE_REVIEW,
            start_time=start_time,
            end_time=end_time,
            context_size_tokens=2500,
            context_completeness=0.9,
            response_time_seconds=5.5,
            suggestions_count=3,
        )

        assert metrics.session_id == "session-123"
        assert metrics.task_type == ClaudeTaskType.CODE_REVIEW
        assert metrics.start_time == start_time
        assert metrics.end_time == end_time
        assert metrics.context_size_tokens == 2500
        assert metrics.context_completeness == 0.9
        assert metrics.response_time_seconds == 5.5
        assert metrics.suggestions_count == 3

    def test_claude_metrics_defaults(self) -> None:
        """Test ClaudeMetrics with default values."""
        metrics = ClaudeMetrics(session_id="session-456", task_type=ClaudeTaskType.DEBUGGING, start_time=time.time())

        assert metrics.session_id == "session-456"
        assert metrics.task_type == ClaudeTaskType.DEBUGGING
        assert metrics.end_time is None
        assert metrics.context_size_tokens == 0
        assert metrics.context_completeness == 0.0
        assert metrics.response_time_seconds == 0.0
        assert metrics.suggestions_count == 0

    def test_claude_metrics_immutability(self) -> None:
        """Test that ClaudeMetrics is immutable."""
        metrics = ClaudeMetrics(session_id="session-789", task_type=ClaudeTaskType.TESTING, start_time=time.time())

        with pytest.raises(AttributeError):
            metrics.session_id = "changed"  # type: ignore[misc]


class TestClaudeWorkflow:
    """Test ClaudeWorkflow class."""

    @pytest.fixture
    def mock_vault(self) -> Mock:
        """Mock SecureVault."""
        return Mock()

    @pytest.fixture
    def mock_collector(self) -> Mock:
        """Mock MetricsCollector."""
        return Mock()

    def test_claude_workflow_creation(self, mock_vault: Mock, mock_collector: Mock) -> None:
        """Test creating ClaudeWorkflow."""
        with (
            patch("devhub.claude_integration.get_global_vault", return_value=mock_vault),
            patch("devhub.claude_integration.get_global_collector", return_value=mock_collector),
        ):
            workflow = ClaudeWorkflow()

            assert isinstance(workflow, ClaudeWorkflow)
            assert hasattr(workflow, "_metrics_collector")
            assert hasattr(workflow, "_vault")

    @pytest.mark.asyncio
    async def test_prepare_code_review_context(self, mock_vault: Mock, mock_collector: Mock) -> None:
        """Test prepare_code_review_context method."""
        with (
            patch("devhub.claude_integration.get_global_vault", return_value=mock_vault),
            patch("devhub.claude_integration.get_global_collector", return_value=mock_collector),
        ):
            workflow = ClaudeWorkflow()

            # Mock the GitHub PR context method
            with (
                patch.object(workflow, "_get_github_pr_context", new_callable=AsyncMock) as mock_github,
                patch.object(workflow, "build_claude_context") as mock_build,
            ):
                mock_github.return_value = {"pr_data": "test"}
                mock_context = ClaudeContext(project_name="test", platform="github")
                mock_build.return_value = mock_context

                result = await workflow.prepare_code_review_context(pr_number=42)

                assert isinstance(result, Success)
                assert result.unwrap() == mock_context

    @pytest.mark.asyncio
    async def test_prepare_debugging_context(self, mock_vault: Mock, mock_collector: Mock) -> None:
        """Test prepare_debugging_context method."""
        with (
            patch("devhub.claude_integration.get_global_vault", return_value=mock_vault),
            patch("devhub.claude_integration.get_global_collector", return_value=mock_collector),
        ):
            workflow = ClaudeWorkflow()

            with patch.object(workflow, "build_claude_context") as mock_build:
                mock_context = ClaudeContext(project_name="test", platform="local")
                mock_build.return_value = mock_context

                result = await workflow.prepare_debugging_context("NullPointerException")

                assert isinstance(result, Success)
                assert result.unwrap() == mock_context


class TestClaudeEnhancer:
    """Test ClaudeEnhancer class."""

    @pytest.fixture
    def mock_vault(self) -> Mock:
        """Mock SecureVault."""
        vault = Mock()
        vault.get_credential.return_value = Success("mock_token")
        return vault

    @pytest.fixture
    def mock_collector(self) -> Mock:
        """Mock MetricsCollector."""
        return Mock()

    @pytest.fixture
    def claude_enhancer(self, mock_vault: Mock, mock_collector: Mock) -> ClaudeEnhancer:
        """Create ClaudeEnhancer with mocked dependencies."""
        with (
            patch("devhub.claude_integration.get_global_vault", return_value=mock_vault),
            patch("devhub.claude_integration.get_global_collector", return_value=mock_collector),
        ):
            return ClaudeEnhancer()

    def test_claude_enhancer_creation(self, claude_enhancer: ClaudeEnhancer) -> None:
        """Test ClaudeEnhancer creation."""
        assert isinstance(claude_enhancer, ClaudeEnhancer)

    @patch("devhub.claude_integration.get_global_vault")
    @patch("devhub.claude_integration.get_global_collector")
    def test_claude_enhancer_initialization(self, mock_get_collector: Mock, mock_get_vault: Mock) -> None:
        """Test ClaudeEnhancer initialization with real calls."""
        mock_vault = Mock()
        mock_collector = Mock()
        mock_get_vault.return_value = mock_vault
        mock_get_collector.return_value = mock_collector

        ClaudeEnhancer()

        # May be called multiple times due to singleton pattern
        assert mock_get_vault.call_count >= 1
        assert mock_get_collector.call_count >= 1


class TestClaudeEnhancerSingleton:
    """Test ClaudeEnhancer singleton pattern."""

    def test_singleton_instance(self) -> None:
        """Test that _ClaudeEnhancerSingleton maintains single instance."""
        singleton = _ClaudeEnhancerSingleton()
        assert singleton._instance is None

        # Get first instance
        with (
            patch("devhub.claude_integration.get_global_vault"),
            patch("devhub.claude_integration.get_global_collector"),
        ):
            instance1 = singleton.get_instance()
            assert instance1 is not None
            assert singleton._instance is instance1

            # Get second instance - should be same
            instance2 = singleton.get_instance()  # type: ignore[unreachable]
            assert instance2 is instance1

    def test_get_claude_enhancer_function(self) -> None:
        """Test get_claude_enhancer function."""
        with (
            patch("devhub.claude_integration.get_global_vault"),
            patch("devhub.claude_integration.get_global_collector"),
        ):
            enhancer1 = get_claude_enhancer()
            enhancer2 = get_claude_enhancer()

            # Should return same instance (singleton)
            assert enhancer1 is enhancer2
            assert isinstance(enhancer1, ClaudeEnhancer)


class TestClaudeIntegrationFunctions:
    """Test top-level Claude integration functions."""

    @pytest.mark.asyncio
    async def test_claude_code_review_context_success(self) -> None:
        """Test claude_code_review_context success case."""
        with patch("devhub.claude_integration.get_claude_enhancer") as mock_get_enhancer:
            mock_enhancer = Mock()
            mock_context = ClaudeContext(project_name="test", platform="github")
            mock_enhancer.get_enhanced_context = AsyncMock(return_value=Success(mock_context))
            mock_get_enhancer.return_value = mock_enhancer

            result = await claude_code_review_context(pr_number=42)

            assert isinstance(result, Success)
            # The function calls to_claude_prompt() on the context
            assert "# Project: test" in result.unwrap()
            mock_enhancer.get_enhanced_context.assert_called_once_with(ClaudeTaskType.CODE_REVIEW, pr_number=42)

    @pytest.mark.asyncio
    async def test_claude_code_review_context_failure(self) -> None:
        """Test claude_code_review_context failure case."""
        with patch("devhub.claude_integration.get_claude_enhancer") as mock_get_enhancer:
            mock_enhancer = Mock()
            mock_enhancer.get_enhanced_context = AsyncMock(return_value=Failure("Context generation failed"))
            mock_get_enhancer.return_value = mock_enhancer

            result = await claude_code_review_context(pr_number=42)

            assert isinstance(result, Failure)
            assert result.failure() == "Context generation failed"

    @pytest.mark.asyncio
    async def test_claude_code_review_context_no_pr(self) -> None:
        """Test claude_code_review_context without PR number."""
        with patch("devhub.claude_integration.get_claude_enhancer") as mock_get_enhancer:
            mock_enhancer = Mock()
            mock_context = ClaudeContext(project_name="test", platform="github")
            mock_enhancer.get_enhanced_context = AsyncMock(return_value=Success(mock_context))
            mock_get_enhancer.return_value = mock_enhancer

            result = await claude_code_review_context()

            assert isinstance(result, Success)
            mock_enhancer.get_enhanced_context.assert_called_once_with(
                ClaudeTaskType.CODE_REVIEW,
                pr_number=0,  # Default value when None is passed
            )

    @pytest.mark.asyncio
    async def test_claude_debugging_context(self) -> None:
        """Test claude_debugging_context function."""
        with patch("devhub.claude_integration.get_claude_enhancer") as mock_get_enhancer:
            mock_enhancer = Mock()
            mock_context = ClaudeContext(project_name="debug-test", platform="local")
            mock_enhancer.get_enhanced_context = AsyncMock(return_value=Success(mock_context))
            mock_get_enhancer.return_value = mock_enhancer

            result = await claude_debugging_context("NullPointerException in parser.py")

            assert isinstance(result, Success)
            assert "# Project: debug-test" in result.unwrap()
            mock_enhancer.get_enhanced_context.assert_called_once_with(
                ClaudeTaskType.DEBUGGING, error_description="NullPointerException in parser.py"
            )

    @pytest.mark.asyncio
    async def test_claude_architecture_context(self) -> None:
        """Test claude_architecture_context function."""
        with patch("devhub.claude_integration.get_claude_enhancer") as mock_get_enhancer:
            mock_enhancer = Mock()
            mock_context = ClaudeContext(
                project_name="arch-test", platform="github", architecture_summary="Microservices"
            )
            mock_enhancer.get_enhanced_context = AsyncMock(return_value=Success(mock_context))
            mock_get_enhancer.return_value = mock_enhancer

            result = await claude_architecture_context()

            assert isinstance(result, Success)
            assert "# Project: arch-test" in result.unwrap()
            assert "Microservices" in result.unwrap()
            mock_enhancer.get_enhanced_context.assert_called_once_with(ClaudeTaskType.ARCHITECTURE)


class TestClaudeContextKwargs:
    """Test ClaudeContextKwargs TypedDict."""

    def test_claude_context_kwargs_typing(self) -> None:
        """Test ClaudeContextKwargs type annotations."""
        # This is primarily a typing test - we verify the TypedDict works correctly
        kwargs: ClaudeContextKwargs = {
            "pr_number": 42,
            "mr_iid": 123,
            "max_tokens": 8000,
            "error_description": "Database connection failed",
            "relevant_files": ["app.py", "database.py"],
        }

        assert kwargs["pr_number"] == 42
        assert kwargs["mr_iid"] == 123
        assert kwargs["max_tokens"] == 8000
        assert kwargs["error_description"] == "Database connection failed"
        assert kwargs["relevant_files"] == ["app.py", "database.py"]

    def test_claude_context_kwargs_partial(self) -> None:
        """Test ClaudeContextKwargs with partial data (total=False)."""
        # Should work with any subset of keys
        kwargs1: ClaudeContextKwargs = {"pr_number": 42}
        kwargs2: ClaudeContextKwargs = {"error_description": "Error occurred"}
        kwargs3: ClaudeContextKwargs = {}

        assert kwargs1["pr_number"] == 42
        assert kwargs2["error_description"] == "Error occurred"
        assert kwargs3 == {}


class TestClaudeIntegrationEdgeCases:
    """Test edge cases and error conditions."""

    def test_claude_context_with_empty_lists(self) -> None:
        """Test ClaudeContext with empty list fields."""
        context = ClaudeContext(
            project_name="test",
            platform="github",
            primary_languages=[],
            recent_commits=[],
            open_pull_requests=[],
            open_issues=[],
            frameworks=[],
        )

        prompt = context.to_claude_prompt()

        # Should not include sections for empty lists
        assert "## Active Pull/Merge Requests" not in prompt
        assert "## Open Issues" not in prompt
        assert "## Tech Stack:" not in prompt
        assert "## Recent Activity" not in prompt

    def test_claude_context_with_many_items(self) -> None:
        """Test ClaudeContext limits items in prompt generation."""
        # Create more than 5 items to test limiting
        many_prs = [{"number": i, "title": f"PR {i}"} for i in range(10)]
        many_issues = [{"number": i, "title": f"Issue {i}"} for i in range(10)]
        many_commits = [{"message": f"Commit {i}"} for i in range(10)]

        context = ClaudeContext(
            project_name="test",
            platform="github",
            open_pull_requests=many_prs,
            open_issues=many_issues,
            recent_commits=many_commits,
        )

        prompt = context.to_claude_prompt()

        # Should limit to 5 PRs and issues, 3 commits
        pr_lines = [line for line in prompt.split("\n") if "- #" in line and "PR" in line]
        issue_lines = [line for line in prompt.split("\n") if "- #" in line and "Issue" in line]
        commit_lines = [line for line in prompt.split("\n") if "- Commit" in line]

        assert len(pr_lines) == 5
        assert len(issue_lines) == 5
        assert len(commit_lines) == 3

    def test_claude_context_with_missing_keys(self) -> None:
        """Test ClaudeContext handles missing keys in dicts gracefully."""
        context = ClaudeContext(
            project_name="test",
            platform="github",
            open_pull_requests=[
                {"title": "PR without number"},
                {"number": 42},  # No title
                {},  # Empty dict
            ],
            open_issues=[
                {"title": "Issue without number"},
                {"iid": 123},  # GitLab style with iid
                {},
            ],
        )

        prompt = context.to_claude_prompt()

        # Should handle missing keys gracefully
        assert "- #?: PR without number" in prompt
        assert "- #42: Untitled" in prompt
        assert "- #?: Untitled" in prompt
        assert "- #123: Untitled" in prompt  # iid used but title is missing

    @pytest.mark.asyncio
    async def test_claude_integration_functions_exception_handling(self) -> None:
        """Test that integration functions handle exceptions properly."""
        with patch("devhub.claude_integration.get_claude_enhancer") as mock_get_enhancer:
            mock_get_enhancer.side_effect = Exception("Enhancer creation failed")

            # Functions should propagate exceptions (not handled in current implementation)
            with pytest.raises(Exception, match="Enhancer creation failed"):
                await claude_code_review_context()

            with pytest.raises(Exception, match="Enhancer creation failed"):
                await claude_debugging_context("error")

            with pytest.raises(Exception, match="Enhancer creation failed"):
                await claude_architecture_context()
