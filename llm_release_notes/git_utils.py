"""Minimal Git helpers used by the tool.

We shell out to `git` to avoid bringing a heavy library; errors are wrapped in
`GitError` and surfaced to callers.
"""

import os
import shutil
import subprocess
import logging
import tempfile
from typing import List, Optional, Tuple

from .exceptions import GitError


def run_git(args: List[str], cwd: Optional[str] = None, check: bool = True) -> str:
    """Run a git command and return stdout. Raises GitError on failure."""
    result = subprocess.run(["git", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode != 0:
        raise GitError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def clone_or_fetch(repo_url: str, workdir: Optional[str] = None) -> str:
    """Create a working copy of the repository ready for checkouts and diffs.

    Uses a light-weight mirror to optimize subsequent fetches.
    Returns path to the working tree.
    """
    tmpdir = workdir or tempfile.mkdtemp(prefix="rn_repo_")
    if os.path.isdir(os.path.join(tmpdir, ".git")):
        run_git(["fetch", "--all", "--tags"], cwd=tmpdir)
        return tmpdir
    run_git(["clone", "--mirror", repo_url, os.path.join(tmpdir, "_mirror")])
    # create a working copy from mirror to speed up subsequent checkouts
    worktree = os.path.join(tmpdir, "work")
    os.makedirs(worktree, exist_ok=True)
    run_git(["init"], cwd=worktree)
    run_git(["remote", "add", "origin", os.path.join(tmpdir, "_mirror")], cwd=worktree)
    run_git(["fetch", "--all", "--tags"], cwd=worktree)
    return worktree


def verify_ref_exists(repo_dir: str, ref: str) -> bool:
    """Return True if the ref exists in the repository."""
    res = subprocess.run(["git", "rev-parse", "--verify", ref], cwd=repo_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.returncode == 0


def checkout_ref(repo_dir: str, ref: str) -> None:
    """Force-checkout the given ref in the working copy."""
    run_git(["checkout", "--force", ref], cwd=repo_dir)


def list_tags(repo_dir: str) -> List[str]:
    """List all tags in the repository as simple strings."""
    out = run_git(["tag"], cwd=repo_dir)
    return [line.strip() for line in out.splitlines() if line.strip()]


def commits_on_range(repo_dir: str, base: str, head: str) -> Tuple[bool, List[str]]:
    """Return (compatible_history, commits_oneline) for base..head.

    If branches do not share a merge-base, returns (False, []).
    """
    # If incompatible history, git rev-list returns non-zero for symmetric difference? Safer: merge-base
    res = subprocess.run(["git", "merge-base", base, head], cwd=repo_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0 or not res.stdout.strip():
        return False, []
    out = run_git(["log", f"{base}..{head}", "--oneline"], cwd=repo_dir)
    return True, [line.rstrip() for line in out.splitlines()]


def diff_between(repo_dir: str, base: str, head: str, exclude_paths: Optional[List[str]] = None, compact: bool = False) -> str:
    """Return a binary-safe unified diff for base..head (no color).

    If exclude_paths are provided, they're passed as repeated pathspec exclusions
    using the ':!path' syntax supported by git to ignore specific paths.
    """
    args = ["diff", f"{base}..{head}", "--binary", "--no-color"]
    if compact: # Remove all context from the diff output.
        args.append("--unified=0")
    if exclude_paths:
        # Use pathspec magic to exclude. Works with Git 2.13+: ':!(path)' or ':!path'
        # We append them after "--" so they are treated as pathspecs.
        args.append("--")
        for p in exclude_paths:
            # Ensure no leading/trailing whitespace
            p = p.strip()
            if p:
                args.append(f":!{p}")
    diff = run_git(args, cwd=repo_dir)
    logging.getLogger(__name__).info("Diff length: %s", len(diff))
    if len(diff) / 4 > 2 ** 19: # estimated 1/2 of the token window of gemini models 
        if not compact:
            logging.getLogger(__name__).info("Diff is very long (estimated %d tokens). Re-running with compact options.", len(diff) / 4)
            return diff_between(repo_dir, base, head, exclude_paths, compact=True)
        else:
            logging.getLogger(__name__).error("Diff is very long (estimated %d tokens). Cutting to length...", len(diff) / 4)
            max_length = 2 ** 19 * 4
            return diff[0:max_length]
    return diff


