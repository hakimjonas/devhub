"""Additional tests for devhub.main untested branches (file writes, save flows)."""

import json
from pathlib import Path
from unittest.mock import patch

from returns.result import Failure
from returns.result import Success

from devhub.main import BundleData
from devhub.main import JiraIssue
from devhub.main import OutputPaths
from devhub.main import Repository
from devhub.main import ReviewComment
from devhub.main import _write_bundle_json
from devhub.main import _write_pr_comments_if_present
from devhub.main import _write_pr_diff_if_present
from devhub.main import _write_pr_markdown
from devhub.main import save_bundle_files


class TestWriteHelpers:
    def test_write_pr_markdown(self):
        pr = {"number": 42, "title": "Add feature", "html_url": "http://example/pr/42", "body": "desc"}
        with patch("devhub.main.write_text_file") as mock_write:
            mock_write.return_value = Success(None)
            paths = OutputPaths(base_dir=Path("/tmp/out"))
            result = _write_pr_markdown(pr, paths)
            assert isinstance(result, Success)
            # Verify write was called with markdown content
            args, _ = mock_write.call_args
            assert args[0].name == "pr_42.md"
            content = args[1]
            assert "Pull Request #42" in content
            assert "Add feature" in content
            assert "http://example/pr/42" in content

    def test_write_pr_diff_if_present_missing(self):
        bundle = BundleData(pr_data={"number": 7})
        paths = OutputPaths(base_dir=Path("/tmp/out"))
        # No diff -> Success without writing
        res = _write_pr_diff_if_present(bundle, 7, paths)
        assert isinstance(res, Success)

    def test_write_pr_diff_if_present_writes(self):
        bundle = BundleData(pr_data={"number": 7}, pr_diff="diff content")
        paths = OutputPaths(base_dir=Path("/tmp/out"))
        with patch("devhub.main.write_text_file") as mock_write:
            mock_write.return_value = Success(None)
            res = _write_pr_diff_if_present(bundle, 7, paths)
            assert isinstance(res, Success)
            args, _ = mock_write.call_args
            assert args[0].name == "pr_7.diff"
            assert args[1] == "diff content"

    def test_write_pr_comments_if_present_missing(self):
        bundle = BundleData(pr_data={"number": 8}, comments=tuple())
        paths = OutputPaths(base_dir=Path("/tmp/out"))
        res = _write_pr_comments_if_present(bundle, 8, paths)
        assert isinstance(res, Success)

    def test_write_pr_comments_if_present_writes(self):
        comments = (
            ReviewComment(
                id="c1", body="Body", path=None, author="me", created_at=None, diff_hunk=None, resolved=False
            ),
        )
        bundle = BundleData(pr_data={"number": 8}, comments=comments)
        paths = OutputPaths(base_dir=Path("/tmp/out"))
        with patch("devhub.main.write_json_file") as mock_write:
            mock_write.return_value = Success(None)
            res = _write_pr_comments_if_present(bundle, 8, paths)
            assert isinstance(res, Success)
            args, _ = mock_write.call_args
            assert args[0].name == "unresolved_comments_pr8.json"
            # Ensure it serializes list of dicts
            assert isinstance(args[1], list)
            assert args[1][0]["id"] == "c1"


class TestSaveBundleFiles:
    def test_save_bundle_files_full_success(self):
        repo = Repository(owner="o", name="n")
        bundle = BundleData(
            jira_issue=JiraIssue(key="T-1", summary="s", description=None, raw_data={}),
            pr_data={"number": 9, "title": "t"},
            pr_diff="d",
            comments=tuple(),
            repository=repo,
            branch="b",
        )
        paths = OutputPaths(base_dir=Path("/tmp/dir"))
        with (
            patch("devhub.main.ensure_directory") as mock_ensure,
            patch("devhub.main.write_json_file") as mock_write_json,
            patch("devhub.main._save_jira_files") as mock_save_jira,
            patch("devhub.main._save_pr_files") as mock_save_pr,
        ):
            mock_ensure.return_value = Success(None)
            mock_write_json.return_value = Success(None)
            mock_save_jira.return_value = Success(None)
            mock_save_pr.return_value = Success(None)
            res = save_bundle_files(bundle, paths)
            assert isinstance(res, Success)
            # write_json_file called with bundle.json dict
            args, _ = mock_write_json.call_args
            assert args[0].name == "bundle.json"
            assert isinstance(args[1], (dict, list))

    def test_save_bundle_files_ensure_dir_failure(self):
        bundle = BundleData()
        paths = OutputPaths(base_dir=Path("/tmp/dir"))
        with patch("devhub.main.ensure_directory") as mock_ensure:
            mock_ensure.return_value = Failure("no dir")
            res = save_bundle_files(bundle, paths)
            assert isinstance(res, Failure)
            assert "no dir" in res.failure()

    def test_write_bundle_json_custom_path(self):
        # Simulate OutputPaths exposing a bundle_json method returning a custom file path
        class CustomPaths:
            def __init__(self, p: Path) -> None:
                self._p = p

            def bundle_json(self) -> Path:
                return self._p / "custom.json"

            @property
            def base_dir(self) -> Path:  # to satisfy attribute usage in fallback
                return self._p

        out = CustomPaths(Path("/tmp/x"))
        # Prepare a minimal valid JSON string
        text = json.dumps({"metadata": {}})
        with (
            patch("devhub.main.ensure_directory") as mock_ensure,
            patch("devhub.main.write_json_file") as mock_write,
        ):
            mock_ensure.return_value = Success(None)
            mock_write.return_value = Success(None)
            res = _write_bundle_json(text, out)  # type: ignore[arg-type]
            assert isinstance(res, Success)
            dest = res.unwrap()
            assert isinstance(dest, Path)
            # Should have ensured parent directory of custom path
            mock_ensure.assert_called_once()
            args, _ = mock_write.call_args
            assert args[0].name == "custom.json"

    def test_write_bundle_json_invalid_text(self):
        out = OutputPaths(base_dir=Path("/tmp/y"))
        res = _write_bundle_json("not json", out)
        assert isinstance(res, Failure)
        assert "Invalid bundle JSON" in res.failure()
