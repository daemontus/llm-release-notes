"""Builds a rich diff context directory for a pair of Git refs.

Outputs include code diff, commit logs, PR discussions, and optional public API diff.
"""

import os
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional

from .git_utils import (
    checkout_ref,
    clone_or_fetch,
    commits_on_range,
    diff_between,
    verify_ref_exists,
)
from .github_api import fetch_pr_discussion


PR_PATTERNS = [
    re.compile(r"\(#(\d+)\)\s*"),  # e.g., "... (#123)"
    re.compile(r"Merge\s+pull\s+request\s+#(\d+)\b", re.IGNORECASE),  # e.g., "Merge pull request #123 ..."
    re.compile(r"pull\s+request\s+#(\d+)\b", re.IGNORECASE),
    re.compile(r"PR\s+#(\d+)\b", re.IGNORECASE),
]


def extract_pr_numbers(commit_message: str) -> List[int]:
    nums: List[int] = []
    for pat in PR_PATTERNS:
        for m in pat.finditer(commit_message):
            try:
                n = int(m.group(1))
                if n not in nums:
                    nums.append(n)
            except Exception:
                continue
    return nums


@dataclass
class DiffContextResult:
    """Metadata about the generated diff context."""
    output_dir: str
    pr_numbers: List[int]
    compatible_history: bool


def write_file(path: str, content: str) -> None:
    """Write text to a file, creating parent directory if necessary."""
    dirpath = os.path.dirname(path)
    if dirpath:
        os.makedirs(dirpath, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def run_public_api_command(repo_dir: str, command: str) -> str:
    """Execute the public API command and capture stdout (stderr ignored)."""
    res = subprocess.run(command, cwd=repo_dir, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.stdout


def generate_diff_context(
    repo_url: str,
    base: str,
    head: str,
    output_dir: str,
    public_api_command: Optional[str] = None,
    diff_exclude_paths: Optional[List[str]] = None,
) -> DiffContextResult:
    repo_dir = clone_or_fetch(repo_url)

    os.makedirs(output_dir, exist_ok=True)

    # Code diff
    logging.getLogger(__name__).info("Computing git diff for %s..%s", base, head)
    # Respect explicitly provided excludes; otherwise best-effort load from repo config
    exclude_paths = diff_exclude_paths
    if exclude_paths is None:
        try:
            from .config import ReleaseNotesConfig as _C
            cfg = _C.load(None, repo_dir)
            exclude_paths = cfg.diff_exclude_paths
        except Exception:
            exclude_paths = None
    if exclude_paths:
        logging.getLogger(__name__).info(
            "Excluding %d path(s) from diff: %s",
            len(exclude_paths),
            ", ".join(exclude_paths),
        )
    code_diff = diff_between(repo_dir, base, head, exclude_paths=exclude_paths)
    write_file(os.path.join(output_dir, "code.diff"), code_diff)

    # Commits and compatibility
    logging.getLogger(__name__).info("Collecting commits for %s..%s", base, head)
    compatible, commits = commits_on_range(repo_dir, base, head)
    if not compatible:
        write_file(os.path.join(output_dir, "commits.log"), "Incompatible history.\n")
        pr_numbers: List[int] = []
    else:
        write_file(os.path.join(output_dir, "commits.log"), "\n".join(commits) + ("\n" if commits else ""))
        pr_numbers = []
        for msg in commits:
            pr_numbers.extend(extract_pr_numbers(msg))
        pr_numbers = sorted(set(pr_numbers))
        logging.getLogger(__name__).info("Detected %d PR(s) in commit messages", len(pr_numbers))

    # Ensure pr_discussions directory exists per spec
    os.makedirs(os.path.join(output_dir, "pr_discussions"), exist_ok=True)

    # Fetch PR discussions as part of diff context (requires GITHUB_TOKEN)
    if pr_numbers:
        pr_dir = os.path.join(output_dir, "pr_discussions")
        for pr in pr_numbers:
            logging.getLogger(__name__).info("Fetching PR discussion #%s", pr)
            discussion = fetch_pr_discussion(repo_url, pr)
            write_file(os.path.join(pr_dir, f"PR-{pr}.txt"), discussion)

    # Optional public API diffs
    if public_api_command:
        # base
        logging.getLogger(__name__).info("Running public API command on base %s", base)
        checkout_ref(repo_dir, base)
        base_api = run_public_api_command(repo_dir, public_api_command)
        write_file(os.path.join(output_dir, "public_api_base.txt"), base_api)
        # head
        logging.getLogger(__name__).info("Running public API command on head %s", head)
        checkout_ref(repo_dir, head)
        head_api = run_public_api_command(repo_dir, public_api_command)
        write_file(os.path.join(output_dir, "public_api_head.txt"), head_api)
        # diff
        # Use unified diff via system diff for readability
        a_path = os.path.join(output_dir, "public_api_base.txt")
        b_path = os.path.join(output_dir, "public_api_head.txt")
        try:
            res = subprocess.run(["diff", "-u", a_path, b_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            write_file(os.path.join(output_dir, "public_api.diff"), res.stdout)
        except FileNotFoundError:
            # diff is not available; fallback simple marker
            write_file(os.path.join(output_dir, "public_api.diff"), "diff tool not available on system\n")

    return DiffContextResult(output_dir=output_dir, pr_numbers=pr_numbers, compatible_history=compatible)


