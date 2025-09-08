import os
from typing import List, Optional

from github import Github


def get_github_client() -> Github:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required to fetch PR discussions")
    return Github(login_or_token=token)


def parse_owner_repo_from_url(repo_url: str) -> Optional[tuple[str, str]]:
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


def fetch_pr_discussion(repo_url: str, pr_number: int) -> str:
    owner_repo = parse_owner_repo_from_url(repo_url)
    if not owner_repo:
        raise RuntimeError("Unsupported GitHub repository URL format")
    owner, repo = owner_repo
    gh = get_github_client()
    repository = gh.get_repo(f"{owner}/{repo}")
    pr = repository.get_pull(pr_number)
    # Collect body and comments
    parts: List[str] = []
    if pr.title:
        parts.append(f"Title: {pr.title}")
    if pr.body:
        parts.append("\nPR Body:\n" + pr.body)
    # Review comments (code) and issue comments (conversation)
    for c in pr.get_issue_comments():
        parts.append(f"\nComment by {c.user.login} at {c.created_at} (issue comment):\n{c.body}")
    for rc in pr.get_review_comments():
        parts.append(f"\nComment by {rc.user.login} at {rc.created_at} (review comment):\n{rc.body}")
    for r in pr.get_reviews():
        if r.body:
            parts.append(f"\nReview by {r.user.login} at {r.submitted_at}:\n{r.body}")
    return "\n".join(parts)


