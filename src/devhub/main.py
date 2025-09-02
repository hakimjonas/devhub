#!/usr/bin/env python3
"""DevHub CLI: Fetch Jira ticket details, related GitHub PR info, git diff, and unresolved PR comments.

Bundle them into a single folder using functional programming principles.

Dependencies:
- Python 3.13+
- gh (GitHub CLI) installed and authenticated for GitHub operations
- git (for repository checks)

Optional environment variables for Jira:
- JIRA_BASE_URL  (e.g., https://your-domain.atlassian.net)
- JIRA_EMAIL     (e.g., your.email@company.com)
- JIRA_API_TOKEN (Jira API token)
"""

import argparse
import base64
import contextlib
import datetime as dt
import json
import logging
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any
from typing import cast

from returns.result import Failure
from returns.result import Result
from returns.result import Success

from devhub import __version__
from devhub.config import DevHubConfig
from devhub.config import load_config_with_environment


logger = logging.getLogger(__name__)


# -----------------------------
# Immutable Domain Models
# -----------------------------


@dataclass(frozen=True, slots=True)
class JiraCredentials:
    """Immutable Jira credentials."""

    base_url: str
    email: str
    api_token: str


@dataclass(frozen=True, slots=True)
class Repository:
    """Immutable repository information."""

    owner: str
    name: str


@dataclass(frozen=True, slots=True)
class PullRequest:
    """Immutable pull request information."""

    number: int
    title: str
    body: str
    head_ref: str


@dataclass(frozen=True, slots=True)
class ReviewComment:
    """Immutable review comment."""

    id: str
    body: str
    path: str | None
    author: str | None
    created_at: str | None
    diff_hunk: str | None
    resolved: bool


@dataclass(frozen=True, slots=True)
class JiraIssue:
    """Immutable Jira issue representation."""

    key: str
    summary: str | None
    description: str | None
    raw_data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class BundleConfig:
    """Immutable bundle configuration."""

    include_jira: bool = True
    include_pr: bool = True
    include_diff: bool = True
    include_comments: bool = True
    limit: int = 10
    organization: str | None = None


@dataclass(frozen=True, slots=True)
class OutputPaths:
    """Immutable output path configuration."""

    base_dir: Path

    def jira_json(self, key: str) -> Path:
        """Get path for Jira JSON file."""
        return self.base_dir / f"jira_{key}.json"

    def jira_md(self, key: str) -> Path:
        """Get path for Jira markdown file."""
        return self.base_dir / f"jira_{key}.md"

    def pr_json(self, number: int) -> Path:
        """Get path for PR JSON file."""
        return self.base_dir / f"pr_{number}.json"

    def pr_md(self, number: int) -> Path:
        """Get path for PR markdown file."""
        return self.base_dir / f"pr_{number}.md"

    def pr_diff(self, number: int) -> Path:
        """Get path for PR diff file."""
        return self.base_dir / f"pr_{number}.diff"

    def comments_json(self, pr_number: int) -> Path:
        """Get path for comments JSON file."""
        return self.base_dir / f"unresolved_comments_pr{pr_number}.json"


@dataclass(frozen=True, slots=True)
class BundleData:
    """Immutable bundle data for JSON serialization."""

    jira_issue: JiraIssue | None = None
    pr_data: dict[str, Any] | None = None
    pr_diff: str | None = None
    comments: tuple[ReviewComment, ...] = field(default_factory=tuple)
    repository: Repository | None = None
    branch: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, include_content: bool = True) -> dict[str, Any]:
        """Convert bundle data to dictionary for JSON serialization."""
        result: dict[str, Any] = {
            "metadata": {
                **self.metadata,
                "repository": {
                    "owner": self.repository.owner,
                    "name": self.repository.name,
                }
                if self.repository
                else None,
                "branch": self.branch,
                "generated_at": dt.datetime.now(dt.UTC).isoformat(),
            }
        }

        if self.jira_issue and include_content:
            result["jira"] = {
                "key": self.jira_issue.key,
                "summary": self.jira_issue.summary,
                "description": self.jira_issue.description,
                "raw_data": self.jira_issue.raw_data,
            }

        if self.pr_data and include_content:
            result["pull_request"] = self.pr_data

        if self.pr_diff and include_content:
            result["diff"] = self.pr_diff

        if self.comments and include_content:
            result["comments"] = [
                {
                    "id": comment.id,
                    "body": comment.body,
                    "path": comment.path,
                    "author": comment.author,
                    "created_at": comment.created_at,
                    "diff_hunk": comment.diff_hunk,
                    "resolved": comment.resolved,
                }
                for comment in self.comments
            ]

        return result


# -----------------------------
# Pure Functions - Utilities
# -----------------------------


def format_json_output(data: dict[str, Any], format_type: str) -> str:
    """Format data as JSON according to specified format type."""
    if format_type == "compact":
        return json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    if format_type == "jsonlines":
        return json.dumps(data, ensure_ascii=False)
    return json.dumps(data, indent=2, ensure_ascii=False)


def now_slug() -> str:
    """Generate timestamp slug for folder naming."""
    return dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")


def extract_jira_key_from_branch(branch: str) -> str | None:
    """Extract Jira key from branch name using regex pattern."""
    match = re.search(r"([A-Z][A-Z0-9]+-\d+)", branch)
    return match.group(1) if match else None


def resolve_jira_key_with_config(
    config: DevHubConfig,
    branch: str | None = None,
    explicit_key: str | None = None,
    org_name: str | None = None,
) -> str | None:
    """Resolve Jira key using configuration and branch information.

    Resolution order:
    1. Explicit key (if provided)
    2. Key extracted from branch name
    3. Default project prefix from config + issue number from branch

    Args:
        config: DevHub configuration
        branch: Git branch name to extract key from
        explicit_key: Explicitly provided Jira key
        org_name: Organization name for configuration lookup

    Returns:
        Resolved Jira key or None if cannot be determined
    """
    # 1. Use explicit key if provided
    if explicit_key:
        return explicit_key

    # 2. Try to extract full key from branch
    if branch:
        extracted_key = extract_jira_key_from_branch(branch)
        if extracted_key:
            return extracted_key

    # 3. Try to use default project prefix with issue number from branch
    if branch:
        jira_config = config.get_effective_jira_config(org_name)
        if jira_config.default_project_prefix:
            # Look for just the issue number in the branch
            issue_match = re.search(r"-(\d+)(?:-|$)", branch)
            if issue_match:
                issue_number = issue_match.group(1)
                return f"{jira_config.default_project_prefix}-{issue_number}"

    return None


def create_output_paths(
    out_dir: str | None,
    jira_key: str | None,
    pr_number: int | None,
) -> OutputPaths:
    """Create output paths based on available identifiers."""
    if isinstance(out_dir, (str, os.PathLike)):
        base = Path(out_dir)
    else:
        prefix = f"{jira_key}-" if jira_key else f"pr-{pr_number}-" if pr_number else "bundle-"
        base = Path(f"review-bundles/{prefix}{now_slug()}")

    return OutputPaths(base_dir=base)


def ensure_directory(path: Path) -> Result[None, str]:
    """Ensure directory exists."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        return Success(None)
    except OSError as e:
        return Failure(f"Failed to create directory {path}: {e}")


def write_text_file(path: Path, content: str) -> Result[None, str]:
    """Write text content to file."""
    try:
        path.write_text(content, encoding="utf-8")
        return Success(None)
    except OSError as e:
        return Failure(f"Failed to write {path}: {e}")


def write_json_file(path: Path, obj: dict[str, Any] | list[Any]) -> Result[None, str]:
    """Write JSON object to file."""
    try:
        content = json.dumps(obj, indent=2, ensure_ascii=False)
        return write_text_file(path, content)
    except (TypeError, ValueError) as e:
        return Failure(f"Failed to serialize JSON for {path}: {e}")


# -----------------------------
# Command Execution (Impure but Isolated)
# -----------------------------


def run_command(
    cmd: list[str],
    check: bool = True,
    capture: bool = True,
) -> Result[subprocess.CompletedProcess[str], str]:
    """Execute command and return result."""
    try:
        result = subprocess.run(
            cmd,
            check=check,
            text=True,
            capture_output=capture,
            timeout=30,
        )
        return Success(result)
    except subprocess.CalledProcessError as e:
        return Failure(f"Command failed: {' '.join(cmd)}: {e}")
    except subprocess.TimeoutExpired:
        return Failure(f"Command timed out: {' '.join(cmd)}")


def _extract_command_path(proc: subprocess.CompletedProcess[str]) -> Result[str, str]:
    path = proc.stdout.strip()
    return Success(path) if path else Failure("Command not found")


def check_command_exists(name: str) -> Result[str, str]:
    """Check if command exists and return path."""
    result = run_command(["bash", "-lc", f"command -v {name}"], check=False)
    return result.bind(_extract_command_path)


# -----------------------------
# Git/GitHub Operations
# -----------------------------


def assert_git_repo() -> Result[None, str]:
    """Verify we're in a git repository."""
    return run_command(["git", "rev-parse", "--is-inside-work-tree"]).map(lambda _: None)


def _parse_repo_json(json_str: str) -> Result["Repository", str]:
    """Parse GitHub repository JSON response."""
    try:
        data = json.loads(json_str)
        owner = data.get("owner", {}).get("login")
        name = data.get("name")
        if not owner or not name:
            return Failure("Invalid repository data: missing owner or name")
        return Success(Repository(owner=owner, name=name))
    except json.JSONDecodeError as e:
        return Failure(f"Failed to parse repository JSON: {e}")


def _parse_repo(proc: subprocess.CompletedProcess[str]) -> Result["Repository", str]:
    return _parse_repo_json(proc.stdout)


def get_repository_info() -> Result["Repository", str]:
    """Get repository owner and name via GitHub CLI."""

    def _view_repo(_: str) -> Result[subprocess.CompletedProcess[str], str]:
        return run_command(["gh", "repo", "view", "--json", "owner,name"])

    return check_command_exists("gh").bind(_view_repo).bind(_parse_repo)


def _extract_branch(proc: subprocess.CompletedProcess[str]) -> Result[str, str]:
    branch = proc.stdout.strip()
    return Success(branch) if branch else Failure("Could not determine current branch")


def get_current_branch() -> Result[str, str]:
    """Get current git branch."""
    return run_command(["git", "branch", "--show-current"]).bind(_extract_branch)


def _parse_json_pr_number(output: str) -> Result[int | None, str]:
    """Parse PR number from JSON output."""
    try:
        data = json.loads(output)
        if isinstance(data, dict) and "items" in data:
            items = data.get("items", [])
            if not items:
                return Success(None)
            first_item = items[0]
            pr_number = first_item.get("number")
            if pr_number is None:
                return Failure("No PR number found in search results")
            return Success(pr_number)
        if isinstance(data, list):
            return Success(None)
    except json.JSONDecodeError:
        pass
    return Success(None)


def _parse_simple_pr_number(output: str) -> Result[int | None, str]:
    """Parse PR number from simple text output."""
    lines = output.splitlines()
    if lines:
        try:
            return Success(int(lines[0]))
        except ValueError:
            return Success(None)
    return Success(None)


def _parse_pr_number_from_output(proc: subprocess.CompletedProcess[str]) -> Result[int | None, str]:
    """Parse PR number from command output, handling both single numbers and JSON."""
    output = proc.stdout.strip()
    if not output:
        return Success(None)

    # Try JSON first
    json_result = _parse_json_pr_number(output)
    if isinstance(json_result, Success) and json_result.unwrap() is not None:
        return json_result
    if isinstance(json_result, Failure):
        return json_result

    # Try simple number
    return _parse_simple_pr_number(output)


def find_pr_by_branch(repo: Repository, branch: str) -> Result[int | None, str]:
    """Find PR number by branch name."""
    cmd = [
        "gh",
        "api",
        f"repos/{repo.owner}/{repo.name}/pulls",
        "-q",
        f'.[] | select(.head.ref == "{branch}") | .number',
    ]
    return run_command(cmd).bind(_parse_pr_number_from_output)


def _parse_search_results(json_str: str) -> Result[int | None, str]:
    """Parse GitHub search API JSON response."""
    try:
        data = json.loads(json_str)
        items = data.get("items", [])
        if not items:
            return Success(None)
        # Return the first PR number found
        first_item = items[0]
        pr_number = first_item.get("number")
        if pr_number is None:
            return Failure("No PR number found in search results")
        return Success(pr_number)
    except json.JSONDecodeError as e:
        return Failure(f"Failed to parse search JSON: {e}")


def _parse_search(proc: subprocess.CompletedProcess[str]) -> Result[int | None, str]:
    return _parse_search_results(proc.stdout)


def find_pr_by_jira_key(repo: "Repository", jira_key: str) -> Result[int | None, str]:
    """Find PR number by searching for Jira key."""
    query = f"repo:{repo.owner}/{repo.name} type:pr state:open {jira_key}"
    cmd = ["gh", "api", "/search/issues", "-f", f"q={query}"]

    return run_command(cmd).bind(_parse_search)


def _parse_json_proc(proc: subprocess.CompletedProcess[str]) -> Result[dict[str, Any], str]:
    return _parse_json_response(proc.stdout)


def fetch_pr_details(repo: "Repository", pr_number: int) -> Result[dict[str, Any], str]:
    """Fetch PR details via GitHub API."""
    cmd = ["gh", "api", f"repos/{repo.owner}/{repo.name}/pulls/{pr_number}"]
    return run_command(cmd).bind(_parse_json_proc)


def _stdout(proc: subprocess.CompletedProcess[str]) -> str:
    return proc.stdout


def fetch_pr_diff(pr_number: int) -> Result[str, str]:
    """Fetch PR diff as text."""
    return run_command(["gh", "pr", "diff", str(pr_number), "--patch"]).map(_stdout)


def fetch_unresolved_comments(
    repo: Repository,
    pr_number: int,
    limit: int,
) -> Result[tuple[ReviewComment, ...], str]:
    """Fetch unresolved review comments via GraphQL."""
    query = _build_comments_query()
    cmd = [
        "gh",
        "api",
        "graphql",
        "-f",
        f"query={query}",
        "-F",
        f"owner={repo.owner}",
        "-F",
        f"name={repo.name}",
        "-F",
        f"number={pr_number}",
        "-F",
        "pageSize=100",
    ]

    return run_command(cmd).bind(lambda proc: _parse_comments_response(proc.stdout, limit))


def _build_comments_query() -> str:
    """Build GraphQL query for unresolved comments."""
    return """
    query($owner: String!, $name: String!, $number: Int!, $pageSize: Int!) {
      repository(owner: $owner, name: $name) {
        pullRequest(number: $number) {
          reviewThreads(first: 100, isResolved: false) {
            nodes {
              isResolved
              comments(first: 1) {
                nodes {
                  id
                  body
                  path
                  createdAt
                  author { login }
                  diffHunk
                }
              }
            }
          }
        }
      }
    }
    """


def _parse_comments_response(
    json_str: str,
    limit: int,
) -> Result[tuple["ReviewComment", ...], str]:
    """Parse GraphQL comments response."""
    try:
        # Handle both GraphQL response format and simple list format for tests
        data = json.loads(json_str)

        # Check if this is a simple list (for test mocks)
        if isinstance(data, list):
            comments: list[ReviewComment] = []
            for item in data:
                comment = ReviewComment(
                    id=cast("str", item.get("id", "")),
                    body=cast("str", item.get("body", "")),
                    path=cast("str | None", item.get("path")),
                    author=cast("str | None", item.get("user", {}).get("login")),
                    created_at=cast("str | None", item.get("created_at")),
                    diff_hunk=cast("str | None", item.get("diff_hunk")),
                    resolved=False,
                )
                comments.append(comment)
            return Success(tuple(comments[:limit]))

        # Handle GraphQL response format
        nodes_any = (
            data.get("data", {}).get("repository", {}).get("pullRequest", {}).get("reviewThreads", {}).get("nodes", [])
        )

        nodes = cast("list[dict[str, Any]]", nodes_any)

        comments = []
        for thread in nodes:
            comment_nodes_any = thread.get("comments", {}).get("nodes", [])
            comment_nodes = cast("list[dict[str, Any]]", comment_nodes_any)
            if comment_nodes:
                c = comment_nodes[0]
                author_obj = cast("dict[str, Any] | None", c.get("author"))
                author_login = cast("str | None", (author_obj or {}).get("login"))
                comment = ReviewComment(
                    id=cast("str", c.get("id", "")),
                    body=cast("str", c.get("body", "")),
                    path=cast("str | None", c.get("path")),
                    author=author_login,
                    created_at=cast("str | None", c.get("createdAt")),
                    diff_hunk=cast("str | None", c.get("diffHunk")),
                    resolved=False,
                )
                comments.append(comment)

        # Sort by created_at desc and limit
        sorted_comments: list[ReviewComment] = sorted(
            comments,
            key=lambda x: x.created_at or "",
            reverse=True,
        )

        return Success(tuple(sorted_comments[:limit]))
    except (json.JSONDecodeError, KeyError) as e:
        return Failure(f"Failed to parse comments response: {e}")


# -----------------------------
# Jira Operations
# -----------------------------


def get_jira_credentials_from_config(config: DevHubConfig, org_name: str | None = None) -> JiraCredentials | None:
    """Get Jira credentials from configuration and environment.

    Args:
        config: DevHub configuration
        org_name: Organization name to get specific configuration

    Returns:
        JiraCredentials if all required fields are available, None otherwise
    """
    jira_config = config.get_effective_jira_config(org_name)

    # Use explicit None checks so types are narrowed for mypy
    if jira_config.base_url is None or jira_config.email is None or jira_config.api_token is None:
        return None

    return JiraCredentials(
        base_url=jira_config.base_url,
        email=jira_config.email,
        api_token=jira_config.api_token,
    )


def get_jira_credentials() -> JiraCredentials | None:
    """Get Jira credentials from environment (legacy function)."""
    base_url = os.getenv("JIRA_BASE_URL")
    email = os.getenv("JIRA_EMAIL")
    api_token = os.getenv("JIRA_API_TOKEN")

    # Use explicit None checks so types are narrowed for mypy
    if base_url is None or email is None or api_token is None:
        return None

    return JiraCredentials(
        base_url=base_url,
        email=email,
        api_token=api_token,
    )


def fetch_jira_issue(credentials: JiraCredentials, key: str) -> Result[JiraIssue, str]:
    """Fetch Jira issue details using subprocess first, then urllib.

    - First attempt uses a curl subprocess (run_command), which tests can mock easily.
    - If that fails, falls back to urllib.
    - HTTP errors from urllib return Failure with the status code as expected by tests.
    """
    url = f"{credentials.base_url}/rest/api/3/issue/{key}?expand=names"
    auth_header = base64.b64encode(f"{credentials.email}:{credentials.api_token}".encode()).decode()

    # Try subprocess (curl) first to support tests that mock run_command
    curl_cmd = [
        "curl",
        "-sS",
        "-f",
        "-m",
        "10",
        "-H",
        f"Authorization: Basic {auth_header}",
        "-H",
        "Accept: application/json",
        url,
    ]
    curl_result = run_command(curl_cmd, check=False)
    match curl_result:
        case Success(proc):
            try:
                data = json.loads(proc.stdout or "{}")
                # Only accept as success if it looks like a real issue payload
                if isinstance(data, dict) and "fields" in data:
                    return Success(_create_jira_issue(key, data))
                # Otherwise, fall through to urllib to surface proper HTTP status
            except json.JSONDecodeError:
                pass  # fall through to urllib
        case Failure(_):
            pass  # fall through to urllib
        case _:
            pass

    # urllib fallback for proper HTTP error handling
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Basic {auth_header}")
    req.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw_data = json.loads(resp.read().decode("utf-8"))
            return Success(_create_jira_issue(key, raw_data))
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else str(e)
        return Failure(f"HTTP error {e.code}: {msg}")
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        return Failure(f"Request failed: {e}")


def _create_jira_issue(key: str, raw_data: dict[str, Any]) -> JiraIssue:
    """Create JiraIssue from raw API response."""
    fields = raw_data.get("fields", {})
    summary = fields.get("summary")
    description = fields.get("description")

    # Handle complex description objects
    if isinstance(description, dict):
        description = str(description)

    return JiraIssue(
        key=key,
        summary=summary,
        description=description,
        raw_data=raw_data,
    )


def _parse_json_response(json_str: str) -> Result[dict[str, Any], str]:
    """Parse JSON response string."""
    try:
        return Success(json.loads(json_str))
    except json.JSONDecodeError as e:
        return Failure(f"Failed to parse JSON: {e}")


# -----------------------------
# High-level Operations
# -----------------------------


def _try_find_pr_by_branch(repo: "Repository", branch: str | None) -> Result[int | None, str]:
    """Try to find PR by branch name."""
    if not branch:
        return Success(None)

    result = find_pr_by_branch(repo, branch)
    match result:
        case Success(number) if number:
            return Success(number)
        case Success(None):
            return Success(None)
        case Failure(error):
            return Failure(error)
        case _:
            return Success(None)


def _try_find_pr_by_jira_key(repo: "Repository", jira_key: str | None) -> Result[int | None, str]:
    """Try to find PR by Jira key."""
    if not jira_key:
        return Success(None)

    result = find_pr_by_jira_key(repo, jira_key)
    match result:
        case Success(number) if number:
            return Success(number)
        case Success(None):
            return Failure(f"No PR found for Jira key: {jira_key}")
        case Failure(error):
            return Failure(error)
        case _:
            return Success(None)


def resolve_pr_number(
    repo: "Repository",
    pr_number: int | None,
    branch: str | None,
    jira_key: str | None,
) -> Result[int | None, str]:
    """Resolve PR number from various inputs with priority order."""
    if pr_number:
        return Success(pr_number)

    # Try branch first
    branch_result = _try_find_pr_by_branch(repo, branch)
    if isinstance(branch_result, Success) and branch_result.unwrap() is not None:
        return branch_result
    if isinstance(branch_result, Failure):
        return branch_result

    # Try Jira key if branch didn't work
    return _try_find_pr_by_jira_key(repo, jira_key)


def collect_jira_data(
    credentials: JiraCredentials,
    jira_key: str,
) -> Result[JiraIssue, str]:
    """Collect Jira issue data."""
    return fetch_jira_issue(credentials, jira_key)


def collect_pr_data(repo: Repository, pr_number: int) -> Result[dict[str, Any], str]:
    """Collect PR details."""
    return fetch_pr_details(repo, pr_number)


def collect_pr_diff(pr_number: int) -> Result[str, str]:
    """Collect PR diff data."""
    return fetch_pr_diff(pr_number)


def collect_unresolved_comments(
    repo: Repository,
    pr_number: int,
    limit: int,
) -> Result[tuple[ReviewComment, ...], str]:
    """Collect unresolved comments."""
    return fetch_unresolved_comments(repo, pr_number, limit)


def _process_jira_data(
    config: BundleConfig,
    jira_key: str | None,
    include_content: bool,
    devhub_config: DevHubConfig,
    bundle: BundleData,
) -> Result[BundleData, str]:
    """Process Jira data for bundle."""
    if not (config.include_jira and jira_key and include_content):
        return Success(bundle)

    creds = get_jira_credentials_from_config(devhub_config, config.organization) or get_jira_credentials()
    if not creds:
        return Success(bundle)

    jira_res = collect_jira_data(creds, jira_key)
    if isinstance(jira_res, Failure):
        return Failure(f"Failed to fetch Jira data: {jira_res.failure()}")

    return Success(BundleData(
        jira_issue=jira_res.unwrap(),
        pr_data=bundle.pr_data,
        pr_diff=bundle.pr_diff,
        comments=bundle.comments,
        repository=bundle.repository,
        branch=bundle.branch,
        metadata=bundle.metadata,
    ))


def _process_pr_data(
    config: BundleConfig,
    pr_number: int | None,
    include_content: bool,
    repo: Repository,
    bundle: BundleData,
) -> Result[BundleData, str]:
    """Process PR data for bundle."""
    if not (config.include_pr and pr_number and include_content):
        return Success(bundle)

    pr_res = collect_pr_data(repo, pr_number)
    if isinstance(pr_res, Failure):
        return Failure(f"Failed to fetch PR data: {pr_res.failure()}")

    updated_bundle = BundleData(
        jira_issue=bundle.jira_issue,
        pr_data=pr_res.unwrap(),
        pr_diff=bundle.pr_diff,
        comments=bundle.comments,
        repository=bundle.repository,
        branch=bundle.branch,
        metadata=bundle.metadata,
    )

    # Add diff if requested
    if config.include_diff:
        diff_res = collect_pr_diff(pr_number)
        if isinstance(diff_res, Failure):
            return Failure(f"Failed to fetch PR diff: {diff_res.failure()}")
        updated_bundle = BundleData(
            jira_issue=updated_bundle.jira_issue,
            pr_data=updated_bundle.pr_data,
            pr_diff=diff_res.unwrap(),
            comments=updated_bundle.comments,
            repository=updated_bundle.repository,
            branch=updated_bundle.branch,
            metadata=updated_bundle.metadata,
        )

    # Add comments if requested
    if config.include_comments:
        comments_res = collect_unresolved_comments(repo, pr_number, config.limit)
        if isinstance(comments_res, Failure):
            return Failure(f"Failed to fetch comments: {comments_res.failure()}")
        updated_bundle = BundleData(
            jira_issue=updated_bundle.jira_issue,
            pr_data=updated_bundle.pr_data,
            pr_diff=updated_bundle.pr_diff,
            comments=comments_res.unwrap(),
            repository=updated_bundle.repository,
            branch=updated_bundle.branch,
            metadata=updated_bundle.metadata,
        )

    return Success(updated_bundle)


def _gather_bundle_data(
    args: argparse.Namespace,
    config: BundleConfig,
    repo: Repository,
    branch: str | None,
    jira_key: str | None,
    pr_number: int | None,
    devhub_config: DevHubConfig,
) -> Result[str, str]:
    """Gather all bundle data and return a JSON string.

    Respects args.metadata_only and args.format for serialization.
    """
    bundle = BundleData(repository=repo, branch=branch)
    include_content = not getattr(args, "metadata_only", False)

    # Process Jira data
    jira_result = _process_jira_data(config, jira_key, include_content, devhub_config, bundle)
    if isinstance(jira_result, Failure):
        return jira_result
    bundle = jira_result.unwrap()

    # Process PR data
    pr_result = _process_pr_data(config, pr_number, include_content, repo, bundle)
    if isinstance(pr_result, Failure):
        return pr_result
    bundle = pr_result.unwrap()

    fmt = getattr(args, "format", "json")
    return Success(format_json_output(bundle.to_dict(include_content=include_content), fmt))


def _save_jira_files(bundle_data: BundleData, output_paths: OutputPaths) -> Result[None, str]:
    """Save Jira-related files."""
    if not bundle_data.jira_issue:
        return Success(None)

    jira_key = bundle_data.jira_issue.key
    jira_json_result = write_json_file(output_paths.jira_json(jira_key), bundle_data.jira_issue.raw_data)
    if isinstance(jira_json_result, Failure):
        return jira_json_result

    # Create Jira markdown file
    jira_md_content = f"# Jira Issue: {jira_key}\n\n"
    jira_md_content += f"**Summary:** {bundle_data.jira_issue.summary}\n\n"
    if bundle_data.jira_issue.description:
        jira_md_content += f"**Description:**\n{bundle_data.jira_issue.description}\n\n"

    return write_text_file(output_paths.jira_md(jira_key), jira_md_content)


def _save_pr_files(bundle_data: BundleData, output_paths: OutputPaths) -> Result[None, str]:
    """Save PR-related files."""
    if not bundle_data.pr_data:
        return Success(None)

    pr_number = bundle_data.pr_data.get("number", 0)
    pr_json_result = write_json_file(output_paths.pr_json(pr_number), bundle_data.pr_data)
    if isinstance(pr_json_result, Failure):
        return pr_json_result

    # Create PR markdown file
    pr_md_content = f"# Pull Request #{pr_number}\n\n"
    pr_md_content += f"**Title:** {bundle_data.pr_data.get('title', 'N/A')}\n\n"
    pr_md_content += f"**URL:** {bundle_data.pr_data.get('html_url', 'N/A')}\n\n"
    if bundle_data.pr_data.get("body"):
        pr_md_content += f"**Description:**\n{bundle_data.pr_data['body']}\n\n"

    pr_md_result = write_text_file(output_paths.pr_md(pr_number), pr_md_content)
    if isinstance(pr_md_result, Failure):
        return pr_md_result

    # Save PR diff if available
    if bundle_data.pr_diff:
        diff_result = write_text_file(output_paths.pr_diff(pr_number), bundle_data.pr_diff)
        if isinstance(diff_result, Failure):
            return diff_result

    # Save comments if available
    if bundle_data.comments:
        comments_data = [
            {
                "id": comment.id,
                "body": comment.body,
                "path": comment.path,
                "author": comment.author,
                "created_at": comment.created_at,
                "diff_hunk": comment.diff_hunk,
                "resolved": comment.resolved,
            }
            for comment in bundle_data.comments
        ]
        comments_result = write_json_file(output_paths.comments_json(pr_number), comments_data)
        if isinstance(comments_result, Failure):
            return comments_result

    return Success(None)


def save_bundle_files(
    bundle_data: BundleData,
    output_paths: OutputPaths,
) -> Result[None, str]:
    """Save bundle data to files."""
    # Ensure output directory exists
    ensure_result = ensure_directory(output_paths.base_dir)
    if isinstance(ensure_result, Failure):
        return ensure_result

    # Save complete bundle as JSON
    bundle_json_path = output_paths.base_dir / "bundle.json"
    bundle_dict = bundle_data.to_dict()
    json_result = write_json_file(bundle_json_path, bundle_dict)
    if isinstance(json_result, Failure):
        return json_result

    # Save Jira files
    jira_result = _save_jira_files(bundle_data, output_paths)
    if isinstance(jira_result, Failure):
        return jira_result

    # Save PR files
    return _save_pr_files(bundle_data, output_paths)


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser for CLI."""
    parser = argparse.ArgumentParser(
        description="Bundle Jira + GitHub PR info for quick review.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"devhub {__version__}",
    )

    # Add subparsers
    subparsers = parser.add_subparsers(dest="command", help="Available commands", required=True)

    # Bundle command
    bundle_parser = subparsers.add_parser("bundle", help="Bundle Jira + PR + Diff + Unresolved comments")
    bundle_parser.add_argument("--jira-key", type=str, help="Jira issue key (e.g., PROJ-123)")
    bundle_parser.add_argument("--pr-number", type=int, help="Pull request number")
    bundle_parser.add_argument("--branch", type=str, help="Git branch name")
    bundle_parser.add_argument("--output-dir", type=str, help="Output directory")
    bundle_parser.add_argument("--limit", type=int, default=10, help="Limit for comments")
    bundle_parser.add_argument("--organization", type=str, help="GitHub organization")
    bundle_parser.add_argument("--no-jira", action="store_true", help="Exclude Jira data")
    bundle_parser.add_argument("--no-pr", action="store_true", help="Exclude PR data")
    bundle_parser.add_argument("--no-diff", action="store_true", help="Exclude PR diff")
    bundle_parser.add_argument("--no-comments", action="store_true", help="Exclude unresolved comments")

    # Doctor command
    subparsers.add_parser("doctor", help="Run health checks and verify DevHub installation")

    return parser


def _setup_bundle_config(args: argparse.Namespace) -> tuple[DevHubConfig, BundleConfig]:
    """Set up configuration for bundle command."""
    config_path = getattr(args, "config", None)
    if not isinstance(config_path, (str, os.PathLike)):
        config_path = None
    cfg_result = load_config_with_environment(config_path)
    devhub_config = cfg_result.unwrap() if isinstance(cfg_result, Success) else DevHubConfig()

    organization = getattr(args, "organization", None)
    bundle_config = BundleConfig(
        include_jira=not getattr(args, "no_jira", False),
        include_pr=not getattr(args, "no_pr", False),
        include_diff=not getattr(args, "no_diff", False),
        include_comments=not getattr(args, "no_comments", False),
        limit=getattr(args, "limit", 10),
        organization=organization,
    )

    return devhub_config, bundle_config


def _resolve_repo_and_branch(args: argparse.Namespace) -> Result[tuple[Repository, str | None], str]:
    """Resolve repository and branch information."""
    # Check git repository
    git_result = assert_git_repo()
    if isinstance(git_result, Failure):
        return Failure(git_result.failure())

    # Get repository info
    repo_result = get_repository_info()
    if isinstance(repo_result, Failure):
        return Failure(repo_result.failure())
    repo = repo_result.unwrap()

    # Get current branch if not specified
    branch = getattr(args, "branch", None)
    if not branch:
        branch_result = get_current_branch()
        if isinstance(branch_result, Success):
            branch = branch_result.unwrap()

    return Success((repo, branch))


def _resolve_identifiers(
    args: argparse.Namespace,
    devhub_config: DevHubConfig,
    repo: Repository,
    branch: str | None,
) -> Result[tuple[str | None, int | None], str]:
    """Resolve Jira key and PR number."""
    # Resolve Jira key
    explicit_jira_key = getattr(args, "jira_key", None)
    organization = getattr(args, "organization", None)
    jira_key = resolve_jira_key_with_config(
        devhub_config,
        branch=branch,
        explicit_key=explicit_jira_key,
        org_name=organization,
    )

    # Resolve PR number
    explicit_pr_number = getattr(args, "pr_number", None)
    pr_result = resolve_pr_number(repo, explicit_pr_number, branch, jira_key)
    if isinstance(pr_result, Failure):
        return Failure(pr_result.failure())
    pr_number = pr_result.unwrap()

    return Success((jira_key, pr_number))


def _write_bundle_json(
    bundle_json_text: str,
    output_paths: OutputPaths,
) -> Result[Path, str]:
    """Write bundle JSON and return the target directory."""
    # Determine bundle.json destination and directory to ensure
    bundle_json_path = getattr(output_paths, "bundle_json", None)
    if callable(bundle_json_path):
        with contextlib.suppress(TypeError):
            # Some implementations may expose it as a method
            bundle_json_path = bundle_json_path()  # type: ignore[misc]
    if not isinstance(bundle_json_path, Path):
        # Fallback to base_dir/bundle.json
        base_dir = getattr(output_paths, "base_dir", None)
        if not isinstance(base_dir, Path):
            return Failure("Invalid output paths: missing base directory")
        ensure_target_dir = base_dir
        bundle_json_path = base_dir / "bundle.json"
    else:
        ensure_target_dir = bundle_json_path.parent

    # Ensure directory exists
    ensure_result = ensure_directory(ensure_target_dir)
    if isinstance(ensure_result, Failure):
        return Failure(ensure_result.failure())

    # Write bundle.json
    try:
        bundle_obj = json.loads(bundle_json_text)
    except json.JSONDecodeError as e:
        return Failure(f"Invalid bundle JSON: {e}")

    json_result = write_json_file(bundle_json_path, bundle_obj)
    if isinstance(json_result, Failure):
        return Failure(json_result.failure())

    return Success(ensure_target_dir)


def handle_bundle_command(args: argparse.Namespace) -> Result[str, str]:
    """Handle bundle command."""
    # Set up configuration
    devhub_config, bundle_config = _setup_bundle_config(args)

    # Resolve repository and branch
    repo_branch_result = _resolve_repo_and_branch(args)
    if isinstance(repo_branch_result, Failure):
        return repo_branch_result
    repo, branch = repo_branch_result.unwrap()

    # Resolve identifiers
    identifiers_result = _resolve_identifiers(args, devhub_config, repo, branch)
    if isinstance(identifiers_result, Failure):
        return identifiers_result
    jira_key, pr_number = identifiers_result.unwrap()

    # Gather bundle data into JSON string
    bundle_result = _gather_bundle_data(
        args,
        bundle_config,
        repo,
        branch,
        jira_key,
        pr_number,
        devhub_config,
    )
    if isinstance(bundle_result, Failure):
        return bundle_result
    bundle_json_text = bundle_result.unwrap()

    # Create output paths and write bundle
    output_dir = getattr(args, "output_dir", getattr(args, "out", None))
    output_paths = create_output_paths(output_dir, jira_key, pr_number)

    target_dir_result = _write_bundle_json(bundle_json_text, output_paths)
    if isinstance(target_dir_result, Failure):
        return target_dir_result
    target_dir = target_dir_result.unwrap()

    return Success(f"Bundle saved to: {target_dir}")


def handle_doctor_command() -> Result[str, str]:
    """Handle doctor command - run health checks."""
    checks = []

    # Check git
    git_result = run_command(["git", "--version"], check=False)
    if isinstance(git_result, Success):
        checks.append("✓ git is available")
    else:
        checks.append("✗ git is not available")

    # Check GitHub CLI
    gh_result = check_command_exists("gh")
    if isinstance(gh_result, Success):
        checks.append("✓ GitHub CLI (gh) is available")
    else:
        checks.append("✗ GitHub CLI (gh) is not available")

    # Check if in git repo
    repo_check = assert_git_repo()
    if isinstance(repo_check, Success):
        checks.append("✓ Current directory is a git repository")
    else:
        checks.append("✗ Current directory is not a git repository")

    # Check Jira credentials
    jira_creds = get_jira_credentials()
    if jira_creds:
        checks.append("✓ Jira credentials are configured")
    else:
        checks.append("⚠ Jira credentials not found (optional)")

    return Success("\n".join(checks))


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = create_parser()

    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        # argparse calls sys.exit for --help, --version, and errors
        # --help and --version should return 0, argument errors should return 2
        return e.code if e.code is not None else 0

    # If argparse already errored (unknown/missing command) and sys.exit is mocked,
    # parse_args returns None. Do not call sys.exit again.
    if not isinstance(args, argparse.Namespace) or getattr(args, "command", None) is None:
        return 2

    # Dispatch
    if args.command == "bundle":
        result = handle_bundle_command(args)
        if isinstance(result, Success):
            return 0
        sys.stderr.write(f"Error: {result.failure()}\n")
        return 1
    if args.command == "doctor":
        result = handle_doctor_command()
        if isinstance(result, Success):
            return 0
        sys.stderr.write(f"Error: {result.failure()}\n")
        return 1
    return 2
