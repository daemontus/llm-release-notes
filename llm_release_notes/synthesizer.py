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
    # returns list of (base, head) pairs
    t_info = parse_semver_tag(target_version)
    assert t_info
    major, minor, patch = t_info
    semver_sorted = list_semver_tags_sorted(all_tags)
    target_vi = semver.VersionInfo(*t_info)
    # Find previous tags (as tag strings) strictly less than target
    previous_tags = [tag for vi, tag in semver_sorted if tag != target_version and vi < target_vi]

    if patch != 0:
        # bugfix: immediately preceding tag on same minor
        preceding_same_minor = None
        for t in reversed(previous_tags):
            m, n, p = parse_semver_tag(t)  # type: ignore
            if m == major and n == minor:
                preceding_same_minor = t
                break
        return [(preceding_same_minor, target_version)] if preceding_same_minor else []

    if minor != 0:
        # minor: latest preceding tag and previous minor base
        latest_preceding = previous_tags[-1] if previous_tags else None
        previous_minor_base = f"v{major}.{minor-1}.0" if minor > 0 else None
        comps: List[Tuple[str, str]] = []
        seen_bases: set[str] = set()
        if latest_preceding and latest_preceding not in seen_bases:
            comps.append((latest_preceding, target_version))
            seen_bases.add(latest_preceding)
        if previous_minor_base and any(tag == previous_minor_base for _, tag in semver_sorted) and previous_minor_base not in seen_bases:
            comps.append((previous_minor_base, target_version))
            seen_bases.add(previous_minor_base)
        return comps

    # major
    latest_preceding = previous_tags[-1] if previous_tags else None
    previous_minor_base = f"v{major-1}.x"  # not a tag; derive last minor of previous major
    prev_major_base = f"v{major-1}.0.0" if major > 0 else None
    comps: List[Tuple[str, str]] = []
    seen_bases: set[str] = set()
    if latest_preceding and latest_preceding not in seen_bases:
        comps.append((latest_preceding, target_version))
        seen_bases.add(latest_preceding)
    # previous major base: exact tag
    if prev_major_base and any(tag == prev_major_base for _, tag in semver_sorted) and prev_major_base not in seen_bases:
        comps.append((prev_major_base, target_version))
        seen_bases.add(prev_major_base)
    # previous minor base: best-effort pick highest v{major-1}.X.0
    if major > 0:
        candidates = [tag for vi, tag in semver_sorted if vi.major == major - 1 and vi.patch == 0]
        if candidates and candidates[-1] not in seen_bases:
            comps.append((candidates[-1], target_version))
    return comps


def build_llm_files_list(context_dir: str) -> List[str]:
    files = []
    for name in ("code.diff", "commits.log", "public_api.diff", "public_api_base.txt", "public_api_head.txt"):
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
    _ctx = generate_diff_context(repo_url, base, head, temp_output_dir, public_api_command=config.public_api_command)
    # choose prompt
    change_type = determine_change_type(head)
    prompt = config.prompts.get(config.project_type, {}).get(change_type) or config.prompts["library"][change_type]
    # call LLM
    files = build_llm_files_list(temp_output_dir)
    names = [ os.path.basename(f) for f in files ]
    logging.getLogger(__name__).info("Calling LLM with %d context file(s): %s", len(files), str(names))
    model_name = getattr(config, "model_name", "gemini-2.5-flash")
    return generate_text_from_context(prompt, files, model=model_name)


