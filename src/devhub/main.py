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
import datetime as dt
import json
import logging
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
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
    if out_dir:
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


def find_pr_by_branch(repo: Repository, branch: str) -> Result[int | None, str]:
    """Find PR number by branch name."""
    cmd = [
        "gh",
        "api",
        f"repos/{repo.owner}/{repo.name}/pulls",
        "-q",
        f'.[] | select(.head.ref == "{branch}") | .number',
    ]
    return run_command(cmd).map(
        lambda proc: int(proc.stdout.strip().splitlines()[0]) if proc.stdout.strip().splitlines() else None
    )


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
        data = json.loads(json_str)
        nodes_any = (
            data.get("data", {}).get("repository", {}).get("pullRequest", {}).get("reviewThreads", {}).get("nodes", [])
        )

        nodes = cast("list[dict[str, Any]]", nodes_any)

        comments: list[ReviewComment] = []
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
    """Fetch Jira issue details."""
    url = f"{credentials.base_url}/rest/api/3/issue/{key}?expand=names"
    auth_header = base64.b64encode(f"{credentials.email}:{credentials.api_token}".encode()).decode()

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


def resolve_pr_number(
    repo: "Repository",
    pr_number: int | None,
    branch: str | None,
    jira_key: str | None,
) -> Result[int | None, str]:
    """Resolve PR number from various inputs with priority order."""
    if pr_number:
        return Success(pr_number)

    if branch:
        result = find_pr_by_branch(repo, branch)
        match result:
            case Success(number) if number:
                return Success(number)
            case Success(None):
                pass  # Continue to next strategy
            case Failure(error):
                return Failure(error)
            case _:
                pass

    if jira_key:
        return find_pr_by_jira_key(repo, jira_key)

    return Success(None)


def save_jira_bundle(
    paths: OutputPaths,
    issue: JiraIssue,
) -> Result[None, str]:
    """Save Jira issue to files."""
    json_result = write_json_file(paths.jira_json(issue.key), issue.raw_data)

    md_content = f"# Jira {issue.key}\n\n"
    if issue.summary:
        md_content += f"**Summary:** {issue.summary}\n\n"
    if issue.description:
        md_content += f"{issue.description}\n"

    md_result = write_text_file(paths.jira_md(issue.key), md_content)

    # Chain results: if JSON write fails, return that failure; otherwise write MD
    return json_result.bind(lambda _: md_result).map(lambda _: None)


def save_pr_bundle(
    paths: OutputPaths,
    pr_data: dict[str, Any],
    pr_number: int,
    include_diff: bool,
) -> Result[None, str]:
    """Save PR data to files."""
    # Save JSON
    json_result = write_json_file(paths.pr_json(pr_number), pr_data)

    # Save markdown
    title = pr_data.get("title", "")
    body = pr_data.get("body", "")
    md_content = f"# PR #{pr_number}: {title}\n\n{body}\n"
    md_result = write_text_file(paths.pr_md(pr_number), md_content)

    # Save diff if requested
    diff_result: Result[None, str]
    if include_diff:
        diff_result = fetch_pr_diff(pr_number).bind(lambda diff: write_text_file(paths.pr_diff(pr_number), diff))
    else:
        diff_result = Success(None)

    # Combine all results
    results = [json_result, md_result, diff_result]
    for result in results:
        match result:
            case Failure(error):
                return Failure(error)

    return Success(None)


def save_comments_bundle(
    paths: OutputPaths,
    comments: tuple[ReviewComment, ...],
    pr_number: int,
) -> Result[None, str]:
    """Save review comments to JSON file."""
    comments_data = [
        {
            "type": "review_comment",
            "id": comment.id,
            "body": comment.body,
            "path": comment.path,
            "author": comment.author,
            "created_at": comment.created_at,
            "diff_hunk": comment.diff_hunk,
            "resolved": comment.resolved,
        }
        for comment in comments
    ]

    return write_json_file(paths.comments_json(pr_number), comments_data)


# -----------------------------
# Command Handlers
# -----------------------------


def handle_bundle_command(args: argparse.Namespace) -> Result[str, str]:
    """Handle bundle command with functional composition."""
    # Load configuration first
    config_result = load_config_with_environment()
    if isinstance(config_result, Failure):
        logger.warning(f"Failed to load configuration: {config_result.failure()}")
        # Continue with default configuration
        devhub_config = DevHubConfig()
    else:
        devhub_config = config_result.unwrap()

    # Determine organization from args or config
    org_name = getattr(args, "organization", None) or devhub_config.default_organization

    bundle_config = BundleConfig(
        include_jira=not args.no_jira,
        include_pr=not args.no_pr,
        include_diff=not args.no_diff,
        include_comments=not args.no_comments,
        limit=args.limit,
        organization=org_name,
    )

    # Check if JSON output is requested
    if args.format != "files":
        return (
            assert_git_repo()
            .bind(lambda _: get_repository_info())
            .bind(lambda repo: _execute_bundle_json(args, bundle_config, repo, devhub_config))
        )
    return (
        assert_git_repo()
        .bind(lambda _: get_repository_info())
        .bind(lambda repo: _execute_bundle(args, bundle_config, repo, devhub_config))
    )


def _execute_bundle(
    args: argparse.Namespace,
    config: BundleConfig,
    repo: Repository,
    devhub_config: DevHubConfig,
) -> Result[str, str]:
    """Execute bundle operation with all components."""
    # Resolve branch and keys
    branch_result: Result[str, str] = get_current_branch() if not args.branch else Success(args.branch)

    return branch_result.bind(lambda branch: _process_bundle_data(args, config, repo, branch, devhub_config))


def _execute_bundle_json(
    args: argparse.Namespace,
    config: BundleConfig,
    repo: Repository,
    devhub_config: DevHubConfig,
) -> Result[str, str]:
    """Execute bundle operation for JSON output."""
    # Resolve branch and keys
    branch_result: Result[str, str] = get_current_branch() if not args.branch else Success(args.branch)

    return branch_result.bind(lambda branch: _collect_bundle_data_json(args, config, repo, branch, devhub_config))


def _collect_bundle_data_json(
    args: argparse.Namespace,
    config: BundleConfig,
    repo: Repository,
    branch: str,
    devhub_config: DevHubConfig,
) -> Result[str, str]:
    """Collect bundle data and return JSON output."""
    # Use enhanced Jira key resolution with configuration
    jira_key = resolve_jira_key_with_config(
        devhub_config,
        branch=branch,
        explicit_key=args.jira_key,
        org_name=config.organization,
    )

    # Resolve PR number
    pr_result = resolve_pr_number(repo, args.pr, branch, jira_key)

    return pr_result.bind(
        lambda pr_number: _gather_bundle_data(args, config, repo, branch, jira_key, pr_number, devhub_config)
    )


def _process_bundle_data(
    args: argparse.Namespace,
    config: BundleConfig,
    repo: Repository,
    branch: str,
    devhub_config: DevHubConfig,
) -> Result[str, str]:
    """Process and save all bundle data."""
    # Use enhanced Jira key resolution with configuration
    jira_key = resolve_jira_key_with_config(
        devhub_config,
        branch=branch,
        explicit_key=args.jira_key,
        org_name=config.organization,
    )

    # Resolve PR number
    pr_result = resolve_pr_number(repo, args.pr, branch, jira_key)

    return pr_result.bind(lambda pr_number: _save_bundle_files(args, config, repo, jira_key, pr_number, devhub_config))


def _collect_jira_data(
    bundle_data: BundleData, config: BundleConfig, jira_key: str | None, devhub_config: DevHubConfig
) -> BundleData:
    """Collect Jira data and return updated bundle."""
    if not (config.include_jira and jira_key):
        return bundle_data

    credentials = get_jira_credentials_from_config(devhub_config, config.organization)
    if not credentials:
        credentials = get_jira_credentials()

    if not credentials:
        return bundle_data

    jira_result = fetch_jira_issue(credentials, jira_key)
    if isinstance(jira_result, Success):
        return BundleData(
            jira_issue=jira_result.unwrap(),
            pr_data=bundle_data.pr_data,
            pr_diff=bundle_data.pr_diff,
            comments=bundle_data.comments,
            repository=bundle_data.repository,
            branch=bundle_data.branch,
            metadata=bundle_data.metadata,
        )
    return bundle_data


def _collect_pr_data(
    bundle_data: BundleData, config: BundleConfig, repo: Repository, pr_number: int | None
) -> BundleData:
    """Collect PR data and return updated bundle."""
    if not (config.include_pr and pr_number):
        return bundle_data

    pr_result = fetch_pr_details(repo, pr_number)
    if not isinstance(pr_result, Success):
        return bundle_data

    pr_data = pr_result.unwrap()
    pr_diff = None

    if config.include_diff:
        diff_result = fetch_pr_diff(pr_number)
        if isinstance(diff_result, Success):
            pr_diff = diff_result.unwrap()

    return BundleData(
        jira_issue=bundle_data.jira_issue,
        pr_data=pr_data,
        pr_diff=pr_diff,
        comments=bundle_data.comments,
        repository=bundle_data.repository,
        branch=bundle_data.branch,
        metadata=bundle_data.metadata,
    )


def _collect_comments_data(
    bundle_data: BundleData, config: BundleConfig, repo: Repository, pr_number: int | None
) -> BundleData:
    """Collect comments data and return updated bundle."""
    if not (config.include_comments and pr_number):
        return bundle_data

    comments_result = fetch_unresolved_comments(repo, pr_number, config.limit)
    if isinstance(comments_result, Success):
        return BundleData(
            jira_issue=bundle_data.jira_issue,
            pr_data=bundle_data.pr_data,
            pr_diff=bundle_data.pr_diff,
            comments=comments_result.unwrap(),
            repository=bundle_data.repository,
            branch=bundle_data.branch,
            metadata=bundle_data.metadata,
        )
    return bundle_data


def _gather_bundle_data(
    args: argparse.Namespace,
    config: BundleConfig,
    repo: Repository,
    branch: str,
    jira_key: str | None,
    pr_number: int | None,
    devhub_config: DevHubConfig,
) -> Result[str, str]:
    """Gather all bundle data and return formatted JSON."""
    bundle_data = BundleData(
        repository=repo,
        branch=branch,
        metadata={
            "config": {
                "include_jira": config.include_jira,
                "include_pr": config.include_pr,
                "include_diff": config.include_diff,
                "include_comments": config.include_comments,
                "limit": config.limit,
            },
            "jira_key": jira_key,
            "pr_number": pr_number,
        },
    )

    # Collect data through functional composition
    bundle_data = _collect_jira_data(bundle_data, config, jira_key, devhub_config)
    bundle_data = _collect_pr_data(bundle_data, config, repo, pr_number)
    bundle_data = _collect_comments_data(bundle_data, config, repo, pr_number)

    # Convert to JSON and format
    include_content = not args.metadata_only
    data_dict = bundle_data.to_dict(include_content=include_content)
    json_output = format_json_output(data_dict, args.format)

    return Success(json_output)


def _save_bundle_files(
    args: argparse.Namespace,
    config: BundleConfig,
    repo: Repository,
    jira_key: str | None,
    pr_number: int | None,
    devhub_config: DevHubConfig,
) -> Result[str, str]:
    """Save all bundle files and return success message."""
    paths = create_output_paths(args.out, jira_key, pr_number)

    return (
        ensure_directory(paths.base_dir)
        .bind(lambda _: _save_jira_if_requested(paths, config, jira_key, devhub_config))
        .bind(lambda _: _save_pr_if_requested(paths, config, repo, pr_number))
        .bind(lambda _: _save_comments_if_requested(paths, config, repo, pr_number))
        .map(lambda _: f"Bundle saved to: {paths.base_dir}")
    )


def _save_issue(paths: "OutputPaths", issue: "JiraIssue") -> Result[None, str]:
    return save_jira_bundle(paths, issue)


def _save_pr(paths: "OutputPaths", pr_number: int, include_diff: bool) -> Callable[[dict[str, Any]], Result[None, str]]:
    def inner(pr_data: dict[str, Any]) -> Result[None, str]:
        return save_pr_bundle(paths, pr_data, pr_number, include_diff)

    return inner


def _save_comments(paths: "OutputPaths", pr_number: int) -> Callable[[tuple["ReviewComment", ...]], Result[None, str]]:
    def inner(comments: tuple["ReviewComment", ...]) -> Result[None, str]:
        return save_comments_bundle(paths, comments, pr_number)

    return inner


def _save_jira_if_requested(
    paths: "OutputPaths",
    config: "BundleConfig",
    jira_key: str | None,
    devhub_config: DevHubConfig,
) -> Result[None, str]:
    """Save Jira data if requested and available."""
    if not config.include_jira or not jira_key:
        return Success(None)

    # Try configuration-based credentials first, then fallback to environment
    credentials = get_jira_credentials_from_config(devhub_config, config.organization)
    if not credentials:
        credentials = get_jira_credentials()

    if not credentials:
        logger.warning("Jira credentials not set in configuration or environment. Skipping Jira fetch.")
        return Success(None)

    return fetch_jira_issue(credentials, jira_key).bind(lambda issue: _save_issue(paths, issue))


def _save_pr_if_requested(
    paths: "OutputPaths",
    config: "BundleConfig",
    repo: "Repository",
    pr_number: int | None,
) -> Result[None, str]:
    """Save PR data if requested and available."""
    if not config.include_pr or not pr_number:
        return Success(None)

    return fetch_pr_details(repo, pr_number).bind(_save_pr(paths, pr_number, config.include_diff))


def _save_comments_if_requested(
    paths: "OutputPaths",
    config: "BundleConfig",
    repo: "Repository",
    pr_number: int | None,
) -> Result[None, str]:
    """Save comments if requested and available."""
    if not config.include_comments or not pr_number:
        return Success(None)

    return fetch_unresolved_comments(repo, pr_number, config.limit).bind(_save_comments(paths, pr_number))


# -----------------------------
# CLI Setup and Main
# -----------------------------


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser with all commands."""
    parser = argparse.ArgumentParser(
        prog="devhub",
        description="Bundle Jira + GitHub PR info for quick review.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Bundle command
    bundle_parser = subparsers.add_parser(
        "bundle",
        help="Bundle Jira + PR + Diff + Unresolved comments",
    )
    _add_bundle_arguments(bundle_parser)

    return parser


def _add_bundle_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments for bundle command."""
    parser.add_argument("--out", help="Output directory")
    parser.add_argument("--branch", help="Branch name to locate PR or infer Jira key")
    parser.add_argument("--jira-key", help="Jira issue key (e.g., ABC-1234)")
    parser.add_argument("--pr", type=int, help="PR number")
    parser.add_argument("--limit", type=int, default=10, help="Limit for unresolved comments")

    # Output format options for agents
    parser.add_argument(
        "--format",
        choices=["files", "json", "compact", "jsonlines"],
        default="files",
        help="Output format: files (default), json, compact (single-line JSON), or jsonlines",
    )
    parser.add_argument("--stdout", action="store_true", help="Output to stdout instead of files")
    parser.add_argument("--metadata-only", action="store_true", help="Include only metadata, no file contents")

    # Exclusion flags
    parser.add_argument("--no-jira", action="store_true", help="Exclude Jira details")
    parser.add_argument("--no-pr", action="store_true", help="Exclude PR details")
    parser.add_argument("--no-diff", action="store_true", help="Exclude PR diff")
    parser.add_argument("--no-comments", action="store_true", help="Exclude unresolved comments")


def main(argv: list[str] | None = None) -> int:
    """Main entry point with functional error handling."""
    parser = create_parser()
    args = parser.parse_args(argv)

    if args.command == "bundle":
        result = handle_bundle_command(args)
        match result:
            case Success(message):
                sys.stdout.write(f"{message}\n")
                return 0
            case Failure(error):
                sys.stderr.write(f"Error: {error}\n")
                return 1
            case _:
                # Fallback, shouldn't happen but satisfies exhaustive checking
                sys.stderr.write("Unknown result\n")
                return 1

    sys.stderr.write(f"Unknown command: {args.command}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
