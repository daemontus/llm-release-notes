"""Minimal Git helpers used by the tool.

We shell out to `git` to avoid bringing a heavy library; errors are wrapped in
`GitError` and surfaced to callers.
"""

import atexit
import os
import shutil
import subprocess
import logging
import tempfile
from typing import Dict, List, Optional, Tuple

from .exceptions import GitError


def run_git(args: List[str], cwd: Optional[str] = None, check: bool = True) -> str:
    """Run a git command and return stdout. Raises GitError on failure."""
    result = subprocess.run(["git", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode != 0:
        raise GitError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


# Working copies created by `clone_or_fetch` in this process, keyed by repository URL.
_CLONE_CACHE: Dict[str, str] = {}


def clone_or_fetch(repo_url: str, workdir: Optional[str] = None) -> str:
    """Create a working copy of the repository ready for checkouts and diffs.

    Uses a light-weight mirror to optimize subsequent fetches.
    Returns path to the working tree.

    Without an explicit `workdir`, repeated calls with the same URL reuse the
    working copy created by the first call. Such temporary copies are removed
    when the process exits.
    """
    if workdir is None and repo_url in _CLONE_CACHE:
        return _CLONE_CACHE[repo_url]
    tmpdir = workdir or tempfile.mkdtemp(prefix="rn_repo_")
    mirror = os.path.join(tmpdir, "_mirror")
    worktree = os.path.join(tmpdir, "work")
    if os.path.isdir(os.path.join(worktree, ".git")):
        run_git(["remote", "update", "--prune"], cwd=mirror)
        run_git(["fetch", "--all", "--tags"], cwd=worktree)
        return worktree
    if workdir is None:
        atexit.register(shutil.rmtree, tmpdir, ignore_errors=True)
    run_git(["clone", "--mirror", repo_url, mirror])
    # create a working copy from mirror to speed up subsequent checkouts
    os.makedirs(worktree, exist_ok=True)
    run_git(["init"], cwd=worktree)
    run_git(["remote", "add", "origin", mirror], cwd=worktree)
    run_git(["fetch", "--all", "--tags"], cwd=worktree)
    if workdir is None:
        _CLONE_CACHE[repo_url] = worktree
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


def empty_tree(repo_dir: str) -> str:
    """Return the id of the empty tree (used as the base of a first release)."""
    # Computed rather than hard-coded so that it also works for SHA-256 repositories.
    result = subprocess.run(
        ["git", "hash-object", "-t", "tree", "--stdin"],
        cwd=repo_dir,
        input="",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise GitError(result.stderr.strip() or "git hash-object failed")
    return result.stdout.strip()


def commits_on_range(repo_dir: str, base: Optional[str], head: str) -> Tuple[bool, List[str]]:
    """Return (compatible_history, commits_oneline) for base..head.

    If base is None, returns all commits reachable from head.
    If branches do not share a merge-base, returns (False, []).
    """
    if base is None:
        out = run_git(["log", head, "--oneline"], cwd=repo_dir)
        return True, [line.rstrip() for line in out.splitlines()]
    res = subprocess.run(["git", "merge-base", base, head], cwd=repo_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0 or not res.stdout.strip():
        return False, []
    out = run_git(["log", f"{base}..{head}", "--oneline"], cwd=repo_dir)
    return True, [line.rstrip() for line in out.splitlines()]


def diff_between(
    repo_dir: str,
    base: Optional[str],
    head: str,
    exclude_paths: Optional[List[str]] = None,
    compact: bool = False,
) -> str:
    """Return a binary-safe unified diff between base and head (no color).

    If base is None, the diff is computed against an empty repository.
    If compact is set, the diff contains no context lines.
    If exclude_paths are provided, they're passed as repeated pathspec exclusions
    using the ':!path' syntax supported by git to ignore specific paths.
    """
    args = ["diff", base or empty_tree(repo_dir), head, "--binary", "--no-color"]
    if compact:
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
    return diff
