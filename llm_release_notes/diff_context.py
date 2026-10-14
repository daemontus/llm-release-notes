"""Builds a rich diff context directory for a pair of Git refs.

Outputs include code diff, commit logs, PR discussions, and optional public API diff.
"""

import difflib
import os
import logging
import re
import subprocess
from dataclasses import dataclass
from typing import List, Optional

from .git_utils import (
    checkout_ref,
    clone_or_fetch,
    commits_on_range,
    diff_between,
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
    """Execute the public API command and capture stdout (stderr is only logged on failure)."""
    res = subprocess.run(command, cwd=repo_dir, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        logging.getLogger(__name__).warning(
            "Public API command exited with code %d; the API diff may be incomplete. Stderr:\n%s",
            res.returncode,
            res.stderr.strip(),
        )
    return res.stdout


def generate_diff_context(
    repo_url: str,
    base: Optional[str],
    head: str,
    output_dir: str,
    public_api_command: Optional[str] = None,
    diff_exclude_paths: Optional[List[str]] = None,
) -> DiffContextResult:
    """Write the diff context for base..head into output_dir.

    If base is None, head is compared against an empty repository (first release).
    """
    repo_dir = clone_or_fetch(repo_url)
    range_name = f"{base}..{head}" if base else f"(empty)..{head}"

    os.makedirs(output_dir, exist_ok=True)

    # Code diff
    logging.getLogger(__name__).info("Computing git diff for %s", range_name)
    exclude_paths = diff_exclude_paths
    if exclude_paths:
        logging.getLogger(__name__).info(
            "Excluding %d path(s) from diff: %s",
            len(exclude_paths),
            ", ".join(exclude_paths),
        )
    code_diff = diff_between(repo_dir, base, head, exclude_paths=exclude_paths)
    write_file(os.path.join(output_dir, "code.diff"), code_diff)

    # Commits and compatibility
    logging.getLogger(__name__).info("Collecting commits for %s", range_name)
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
            if discussion is None:
                continue
            write_file(os.path.join(pr_dir, f"PR-{pr}.txt"), discussion)

    # Optional public API diffs
    if public_api_command:
        # base (an empty repository has no public API)
        if base:
            logging.getLogger(__name__).info("Running public API command on base %s", base)
            checkout_ref(repo_dir, base)
            base_api = run_public_api_command(repo_dir, public_api_command)
        else:
            base_api = ""
        write_file(os.path.join(output_dir, "public_api_base.txt"), base_api)
        # head
        logging.getLogger(__name__).info("Running public API command on head %s", head)
        checkout_ref(repo_dir, head)
        head_api = run_public_api_command(repo_dir, public_api_command)
        write_file(os.path.join(output_dir, "public_api_head.txt"), head_api)
        # diff (labels instead of temporary paths and timestamps, which would only be noise for the model)
        api_diff = difflib.unified_diff(
            base_api.splitlines(keepends=True),
            head_api.splitlines(keepends=True),
            fromfile=f"public_api@{base or '(empty)'}",
            tofile=f"public_api@{head}",
        )
        write_file(os.path.join(output_dir, "public_api.diff"), "".join(api_diff))

    return DiffContextResult(output_dir=output_dir, pr_numbers=pr_numbers, compatible_history=compatible)


