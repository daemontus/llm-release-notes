import os
import logging
from typing import List, Optional, Tuple

import semver

from .config import ReleaseNotesConfig, parse_semver_tag
from .diff_context import DiffContextResult, generate_diff_context, write_file
from .gemini_api import generate_text_from_context
from .github_api import fetch_pr_discussion


def determine_change_type(version: str) -> str:
    t = parse_semver_tag(version)
    if not t:
        raise ValueError("Version must be SemVer like vX.Y.Z")
    major, minor, patch = t
    if patch != 0:
        return "bugfix"
    if minor != 0:
        return "minor_change"
    return "major_change"


def list_semver_tags_sorted(tags: List[str]) -> List[tuple[semver.VersionInfo, str]]:
    valid: List[tuple[semver.VersionInfo, str]] = []
    for tag in tags:
        p = parse_semver_tag(tag)
        if p:
            valid.append((semver.VersionInfo(*p), tag))
    valid.sort(key=lambda x: x[0])
    return valid


def select_comparisons_single_version(target_version: str, all_tags: List[str]) -> List[Tuple[str, str]]:
    # returns non-overlapping list of (base, head) pairs in order
    t_info = parse_semver_tag(target_version)
    assert t_info
    major, minor, patch = t_info
    semver_sorted = list_semver_tags_sorted(all_tags)
    target_vi = semver.VersionInfo(*t_info)

    def tag_exists(tag: Optional[str]) -> bool:
        if not tag:
            return False
        return any(t == tag for _, t in semver_sorted)

    # Helper: latest tag matching predicate and < target_vi
    def latest_before(pred) -> Optional[str]:
        for vi, tag in reversed(semver_sorted):
            if vi < target_vi and pred(vi):
                return tag
        return None

    if patch != 0:
        # Bugfix: compare to immediately preceding on same minor branch
        prev_same_minor = latest_before(lambda vi: vi.major == major and vi.minor == minor)
        return [(prev_same_minor, target_version)] if prev_same_minor else []

    if minor != 0:
        # Minor: 1) last bugfix of previous minor vs target, 2) previous minor base vs that bugfix
        last_prev_minor_bugfix = latest_before(lambda vi: vi.major == major and vi.minor == (minor - 1))
        prev_minor_base = f"v{major}.{minor-1}.0" if minor > 0 else None
        comparisons: List[Tuple[str, str]] = []
        if last_prev_minor_bugfix and last_prev_minor_bugfix != target_version:
            comparisons.append((last_prev_minor_bugfix, target_version))
        if tag_exists(prev_minor_base) and last_prev_minor_bugfix and prev_minor_base != last_prev_minor_bugfix:
            comparisons.append((prev_minor_base, last_prev_minor_bugfix))
        return comparisons

    # Major: 1) last bugfix of previous major vs target,
    #        2) highest minor base of previous major vs that bugfix,
    #        3) previous major base vs that minor base
    last_prev_major_bugfix = latest_before(lambda vi: vi.major == (major - 1)) if major > 0 else None
    # Highest minor base in previous major (v{major-1}.{maxMinor}.0)
    prev_major_minor_bases = [
        (vi, tag) for vi, tag in semver_sorted if major > 0 and vi.major == (major - 1) and vi.patch == 0
    ]
    prev_major_minor_base = prev_major_minor_bases[-1][1] if prev_major_minor_bases else None
    prev_major_base = f"v{major-1}.0.0" if major > 0 else None

    comparisons: List[Tuple[str, str]] = []
    if last_prev_major_bugfix and last_prev_major_bugfix != target_version:
        comparisons.append((last_prev_major_bugfix, target_version))
    if prev_major_minor_base and last_prev_major_bugfix and prev_major_minor_base != last_prev_major_bugfix:
        comparisons.append((prev_major_minor_base, last_prev_major_bugfix))
    if tag_exists(prev_major_base) and prev_major_base and prev_major_minor_base and prev_major_base != prev_major_minor_base:
        comparisons.append((prev_major_base, prev_major_minor_base))
    return comparisons


def build_llm_files_list(context_dir: str) -> List[str]:
    files = []
    for name in ("code.diff", "commits.log", "public_api.diff"):
        path = os.path.join(context_dir, name)
        if os.path.isfile(path):
            files.append(path)
    pr_dir = os.path.join(context_dir, "pr_discussions")
    if os.path.isdir(pr_dir):
        for entry in sorted(os.listdir(pr_dir)):
            files.append(os.path.join(pr_dir, entry))
    return files


def synthesize_notes_for_range(
    repo_url: str,
    base: str,
    head: str,
    config: ReleaseNotesConfig,
    temp_output_dir: str,
) -> str:
    logging.getLogger(__name__).info("Generating context for %s..%s", base, head)
    _ctx = generate_diff_context(
        repo_url, 
        base, 
        head, 
        temp_output_dir, 
        public_api_command=config.public_api_command, 
        diff_exclude_paths=config.diff_exclude_paths
    )
    # choose prompt
    change_type = determine_change_type(head)
    base_prompt = config.prompts.get(config.project_type, {}).get(change_type) or config.prompts["library"][change_type]
    if config.project_prompt:
        prompt = base_prompt + "\n\nProject specific instructions:\n" + config.project_prompt
    else:
        prompt = base_prompt
    # call LLM
    files = build_llm_files_list(temp_output_dir)
    names = [ os.path.basename(f) for f in files ]
    logging.getLogger(__name__).info("Calling LLM with %d context file(s): %s", len(files), str(names))
    model_name = getattr(config, "model_name", "gemini-2.5-flash")
    return generate_text_from_context(prompt, files, model=model_name)


