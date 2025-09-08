import os
import shutil
import subprocess
import tempfile
from typing import List, Optional, Tuple


class GitError(RuntimeError):
    pass


def run_git(args: List[str], cwd: Optional[str] = None, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode != 0:
        raise GitError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def clone_or_fetch(repo_url: str, workdir: Optional[str] = None) -> str:
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
    res = subprocess.run(["git", "rev-parse", "--verify", ref], cwd=repo_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.returncode == 0


def checkout_ref(repo_dir: str, ref: str) -> None:
    run_git(["checkout", "--force", ref], cwd=repo_dir)


def list_tags(repo_dir: str) -> List[str]:
    out = run_git(["tag"], cwd=repo_dir)
    return [line.strip() for line in out.splitlines() if line.strip()]


def commits_on_range(repo_dir: str, base: str, head: str) -> Tuple[bool, List[str]]:
    # If incompatible history, git rev-list returns non-zero for symmetric difference? Safer: merge-base
    res = subprocess.run(["git", "merge-base", base, head], cwd=repo_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0 or not res.stdout.strip():
        return False, []
    out = run_git(["log", f"{base}..{head}", "--oneline"], cwd=repo_dir)
    return True, [line.rstrip() for line in out.splitlines()]


def diff_between(repo_dir: str, base: str, head: str) -> str:
    return run_git(["diff", f"{base}..{head}", "--binary", "--no-color"], cwd=repo_dir)


