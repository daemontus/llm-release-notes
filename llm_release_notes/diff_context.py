import os
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
    output_dir: str
    pr_numbers: List[int]
    compatible_history: bool


def write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def run_public_api_command(repo_dir: str, command: str) -> str:
    res = subprocess.run(command, cwd=repo_dir, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.stdout


def generate_diff_context(
    repo_url: str,
    base: str,
    head: str,
    output_dir: str,
    public_api_command: Optional[str] = None,
) -> DiffContextResult:
    repo_dir = clone_or_fetch(repo_url)

    os.makedirs(output_dir, exist_ok=True)

    # Code diff
    code_diff = diff_between(repo_dir, base, head)
    write_file(os.path.join(output_dir, "code.diff"), code_diff)

    # Commits and compatibility
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

    # Ensure pr_discussions directory exists per spec
    os.makedirs(os.path.join(output_dir, "pr_discussions"), exist_ok=True)

    # Fetch PR discussions as part of diff context (requires GITHUB_TOKEN)
    if pr_numbers:
        pr_dir = os.path.join(output_dir, "pr_discussions")
        for pr in pr_numbers:
            discussion = fetch_pr_discussion(repo_url, pr)
            write_file(os.path.join(pr_dir, f"PR-{pr}.txt"), discussion)

    # Optional public API diffs
    if public_api_command:
        # base
        checkout_ref(repo_dir, base)
        base_api = run_public_api_command(repo_dir, public_api_command)
        write_file(os.path.join(output_dir, "public_api_base.txt"), base_api)
        # head
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


