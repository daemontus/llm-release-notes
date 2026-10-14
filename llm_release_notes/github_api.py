"""GitHub API helpers for fetching PR discussions."""

import logging
import os
from typing import List, Optional

from github import Auth, Github, GithubException, UnknownObjectException

from .exceptions import GitHubAPIError


def get_github_client() -> Github:
    """Create an authenticated GitHub client or raise if token missing."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise GitHubAPIError("GITHUB_TOKEN is required to fetch PR discussions")
    return Github(auth=Auth.Token(token))


def parse_owner_repo_from_url(repo_url: str) -> Optional[tuple[str, str]]:
    """Extract (owner, repo) from an SSH or HTTPS GitHub URL."""
    # Supports ssh and https
    # git@github.com:owner/repo.git or https://github.com/owner/repo(.git)
    if repo_url.startswith("git@github.com:"):
        suf = repo_url.split(":", 1)[1]
        if suf.endswith(".git"):
            suf = suf[:-4]
        parts = suf.split("/")
    elif "github.com/" in repo_url:
        suf = repo_url.split("github.com/", 1)[1]
        if suf.endswith(".git"):
            suf = suf[:-4]
        parts = suf.split("/")
    else:
        return None
    if len(parts) >= 2:
        return parts[0], parts[1]
    return None


def _login(user) -> str:
    # Comments from deleted accounts have no user.
    return user.login if user else "ghost"


def fetch_pr_discussion(repo_url: str, pr_number: int) -> Optional[str]:
    """Fetch PR body, issue comments, review comments, and reviews as plain text.

    Returns None if the number does not refer to a pull request (e.g. it is an issue).
    """
    owner_repo = parse_owner_repo_from_url(repo_url)
    if not owner_repo:
        raise GitHubAPIError("Unsupported GitHub repository URL format")
    owner, repo = owner_repo
    gh = get_github_client()
    try:
        repository = gh.get_repo(f"{owner}/{repo}")
        pr = repository.get_pull(pr_number)
    except UnknownObjectException:
        logging.getLogger(__name__).warning("#%s is not a pull request in %s/%s, skipping", pr_number, owner, repo)
        return None
    except GithubException as e:
        raise GitHubAPIError(f"Failed to fetch PR #{pr_number} from {repo_url}: {e}") from e
    # Collect body and comments
    parts: List[str] = []
    if pr.title:
        parts.append(f"Title: {pr.title}")
    if pr.body:
        parts.append("\nPR Body:\n" + pr.body)
    # Review comments (code) and issue comments (conversation)
    try:
        for c in pr.get_issue_comments():
            parts.append(f"\nComment by {_login(c.user)} at {c.created_at} (issue comment):\n{c.body}")
        for rc in pr.get_review_comments():
            parts.append(f"\nComment by {_login(rc.user)} at {rc.created_at} (review comment):\n{rc.body}")
        for r in pr.get_reviews():
            if r.body:
                parts.append(f"\nReview by {_login(r.user)} at {r.submitted_at}:\n{r.body}")
    except GithubException as e:
        raise GitHubAPIError(f"Failed to fetch comments of PR #{pr_number} from {repo_url}: {e}") from e
    return "\n".join(parts)



