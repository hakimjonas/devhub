"""Unit tests for pure utility functions."""

import datetime as dt
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given
from hypothesis import strategies as st

from devhub.main import BundleConfig
from devhub.main import OutputPaths
from devhub.main import create_output_paths
from devhub.main import extract_jira_key_from_branch
from devhub.main import now_slug


class TestPureFunctions:
    """Tests for pure functions with no side effects."""

    def test_extract_jira_key_from_branch_valid(self) -> None:
        """Test Jira key extraction from valid branch names."""
        test_cases = [
            ("feature/ABC-123-add-feature", "ABC-123"),
            ("bugfix/XYZ-456-fix-bug", "XYZ-456"),
            ("ABC-789", "ABC-789"),
            ("feature/PROJECT-1234-long-description", "PROJECT-1234"),
            ("hotfix/TASK-99-urgent-fix", "TASK-99"),
        ]

        for branch, expected in test_cases:
            result = extract_jira_key_from_branch(branch)
            assert result == expected, f"Failed for branch: {branch}"

    def test_extract_jira_key_from_branch_invalid(self) -> None:
        """Test Jira key extraction from invalid branch names."""
        invalid_branches = [
            "feature/no-jira-key",
            "main",
            "develop",
            "feature/abc-123-lowercase",  # Keys should be uppercase
            "feature/A-123-single-letter",  # Keys need at least 2 letters
            "feature/123-ABC-numbers-first",
            "",
            "feature/",
        ]

        for branch in invalid_branches:
            result = extract_jira_key_from_branch(branch)
            assert result is None, f"Should be None for branch: {branch}"

    @given(st.text(min_size=1))
    def test_extract_jira_key_property_based(self, branch_name: str) -> None:
        """Property-based test for Jira key extraction."""
        result = extract_jira_key_from_branch(branch_name)

        # If a result is found, it should match the pattern
        if result is not None:
            assert len(result) >= 4  # At least X-1 format (minimum valid Jira key)
            assert "-" in result
            parts = result.split("-")
            assert len(parts) == 2
            assert parts[0].isupper()  # Project code is uppercase
            assert parts[0].isalnum()  # Project code is alphanumeric (letters and digits)
            assert parts[0][0].isalpha()  # First character must be a letter (per regex)
            assert parts[1].isdigit()  # Issue number is numeric

    def test_now_slug_format(self) -> None:
        """Test that now_slug returns correct format."""
        with patch("devhub.main.dt") as mock_dt:
            # Create a mock datetime
            mock_datetime = dt.datetime(2024, 1, 15, 14, 30, 45, tzinfo=dt.UTC)
            mock_dt.datetime.now.return_value = mock_datetime
            mock_dt.UTC = dt.UTC

            result = now_slug()
            assert result == "20240115-143045"

    def test_now_slug_is_deterministic_at_same_time(self) -> None:
        """Test that now_slug is deterministic when called at the same time."""
        with patch("devhub.main.dt") as mock_dt:
            mock_datetime = dt.datetime(2024, 1, 15, 14, 30, 45, tzinfo=dt.UTC)
            mock_dt.datetime.now.return_value = mock_datetime
            mock_dt.UTC = dt.UTC

            result1 = now_slug()
            result2 = now_slug()
            assert result1 == result2

    def test_create_output_paths_with_custom_dir(self) -> None:
        """Test output path creation with custom directory."""
        custom_dir = "/custom/path"
        paths = create_output_paths(custom_dir, None, None)

        assert paths.base_dir == Path(custom_dir)

    def test_create_output_paths_with_jira_key(self) -> None:
        """Test output path creation with Jira key."""
        with patch("devhub.main.now_slug", return_value="20240115-143045"):
            paths = create_output_paths(None, "ABC-123", None)

            expected_base = Path("review-bundles/ABC-123-20240115-143045")
            assert paths.base_dir == expected_base

    def test_create_output_paths_with_pr_number(self) -> None:
        """Test output path creation with PR number."""
        with patch("devhub.main.now_slug", return_value="20240115-143045"):
            paths = create_output_paths(None, None, 456)

            expected_base = Path("review-bundles/pr-456-20240115-143045")
            assert paths.base_dir == expected_base

    def test_create_output_paths_default(self) -> None:
        """Test output path creation with defaults."""
        with patch("devhub.main.now_slug", return_value="20240115-143045"):
            paths = create_output_paths(None, None, None)

            expected_base = Path("review-bundles/bundle-20240115-143045")
            assert paths.base_dir == expected_base

    def test_create_output_paths_priority_order(self) -> None:
        """Test that Jira key takes priority over PR number."""
        with patch("devhub.main.now_slug", return_value="20240115-143045"):
            paths = create_output_paths(None, "ABC-123", 456)

            # Jira key should take priority
            expected_base = Path("review-bundles/ABC-123-20240115-143045")
            assert paths.base_dir == expected_base


class TestOutputPaths:
    """Tests for OutputPaths immutable data structure."""

    def test_output_paths_immutable(self) -> None:
        """Test that OutputPaths is immutable."""
        base_dir = Path("/test/path")
        paths = OutputPaths(base_dir=base_dir)

        # This should work
        assert paths.base_dir == base_dir

        # Attempting to modify should fail (frozen dataclass)
        with pytest.raises((AttributeError, TypeError)):
            # This should fail because it's a frozen dataclass
            paths.base_dir = Path("/other/path")  # type: ignore[misc]

    def test_output_paths_jira_json(self) -> None:
        """Test Jira JSON path generation."""
        paths = OutputPaths(base_dir=Path("/test"))
        result = paths.jira_json("ABC-123")
        assert result == Path("/test/jira_ABC-123.json")

    def test_output_paths_jira_md(self) -> None:
        """Test Jira markdown path generation."""
        paths = OutputPaths(base_dir=Path("/test"))
        result = paths.jira_md("ABC-123")
        assert result == Path("/test/jira_ABC-123.md")

    def test_output_paths_pr_json(self) -> None:
        """Test PR JSON path generation."""
        paths = OutputPaths(base_dir=Path("/test"))
        result = paths.pr_json(456)
        assert result == Path("/test/pr_456.json")

    def test_output_paths_pr_md(self) -> None:
        """Test PR markdown path generation."""
        paths = OutputPaths(base_dir=Path("/test"))
        result = paths.pr_md(456)
        assert result == Path("/test/pr_456.md")

    def test_output_paths_pr_diff(self) -> None:
        """Test PR diff path generation."""
        paths = OutputPaths(base_dir=Path("/test"))
        result = paths.pr_diff(456)
        assert result == Path("/test/pr_456.diff")

    def test_output_paths_comments_json(self) -> None:
        """Test comments JSON path generation."""
        paths = OutputPaths(base_dir=Path("/test"))
        result = paths.comments_json(456)
        assert result == Path("/test/unresolved_comments_pr456.json")


class TestBundleConfig:
    """Tests for BundleConfig immutable configuration."""

    def test_bundle_config_defaults(self) -> None:
        """Test BundleConfig default values."""
        config = BundleConfig()

        assert config.include_jira is True
        assert config.include_pr is True
        assert config.include_diff is True
        assert config.include_comments is True
        assert config.limit == 10

    def test_bundle_config_custom_values(self) -> None:
        """Test BundleConfig with custom values."""
        config = BundleConfig(
            include_jira=False,
            include_pr=True,
            include_diff=False,
            include_comments=True,
            limit=20,
        )

        assert config.include_jira is False
        assert config.include_pr is True
        assert config.include_diff is False
        assert config.include_comments is True
        assert config.limit == 20

    def test_bundle_config_immutable(self) -> None:
        """Test that BundleConfig is immutable."""
        config = BundleConfig()

        # Attempting to modify should fail (frozen dataclass)
        with pytest.raises((AttributeError, TypeError)):
            # This should fail because it's a frozen dataclass
            config.include_jira = False  # type: ignore[misc]

    @given(
        include_jira=st.booleans(),
        include_pr=st.booleans(),
        include_diff=st.booleans(),
        include_comments=st.booleans(),
        limit=st.integers(min_value=1, max_value=100),
    )
    def test_bundle_config_property_based(
        self,
        include_jira: bool,
        include_pr: bool,
        include_diff: bool,
        include_comments: bool,
        limit: int,
    ) -> None:
        """Property-based test for BundleConfig creation."""
        config = BundleConfig(
            include_jira=include_jira,
            include_pr=include_pr,
            include_diff=include_diff,
            include_comments=include_comments,
            limit=limit,
        )

        # All properties should match input
        assert config.include_jira == include_jira
        assert config.include_pr == include_pr
        assert config.include_diff == include_diff
        assert config.include_comments == include_comments
        assert config.limit == limit

        # Object should be hashable and immutable
        assert isinstance(config, BundleConfig)
        # Immutability is already tested in test_bundle_config_immutable
