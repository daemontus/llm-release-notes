import os
import logging
from typing import List, Optional, Tuple

import semver

from .config import ReleaseNotesConfig, parse_semver_tag
from .context_budget import estimate_tokens, fit_context, tokens_to_chars
from .diff_context import generate_diff_context
from .exceptions import ConfigError, llmReleaseNotesError
from .git_utils import clone_or_fetch, diff_between
from .llm_api import generate_text


CODE_DIFF = "code.diff"
MAX_NOTES_CHARS = 500


def determine_change_type(version: str, initial: bool = False) -> str:
    t = parse_semver_tag(version)
    if not t:
        raise llmReleaseNotesError(f"Version must be SemVer like vX.Y.Z, got '{version}'")
    if initial:
        return "initial_release"
    major, minor, patch = t
    if patch != 0:
        return "bugfix"
    if minor != 0:
        return "minor_change"
    return "major_change"


def list_semver_tags_sorted(tags: List[str]) -> List[tuple[semver.Version, str]]:
    valid: List[tuple[semver.Version, str]] = []
    for tag in tags:
        p = parse_semver_tag(tag)
        if p:
            valid.append((semver.Version(*p), tag))
    valid.sort(key=lambda x: x[0])
    return valid


def select_comparisons_single_version(target_version: str, all_tags: List[str]) -> List[Tuple[Optional[str], str]]:
    """Return a non-overlapping list of (base, head) pairs, newest first.

    A base of None means "empty repository", which is used for the first release.
    """
    t_info = parse_semver_tag(target_version)
    if not t_info:
        raise llmReleaseNotesError(f"Version must be SemVer like vX.Y.Z, got '{target_version}'")
    major, minor, patch = t_info
    semver_sorted = list_semver_tags_sorted(all_tags)
    target_vi = semver.Version(*t_info)

    # Helper: latest tag matching predicate and < target_vi
    def latest_before(pred) -> Optional[str]:
        for vi, tag in reversed(semver_sorted):
            if vi < target_vi and pred(vi):
                return tag
        return None

    # Helper: actual tag name for a version (handles both 'vX.Y.Z' and 'X.Y.Z' tags)
    def find_tag(major: int, minor: int, patch: int) -> Optional[str]:
        for vi, tag in semver_sorted:
            if (vi.major, vi.minor, vi.patch) == (major, minor, patch):
                return tag
        return None

    latest_any = latest_before(lambda vi: True)
    if latest_any is None:
        # First release: compare against an empty repository.
        return [(None, target_version)]

    comparisons: List[Tuple[Optional[str], str]] = []
    if patch != 0:
        # Bugfix: compare to immediately preceding on same minor branch
        prev_same_minor = latest_before(lambda vi: vi.major == major and vi.minor == minor)
        if prev_same_minor:
            comparisons.append((prev_same_minor, target_version))
    elif minor != 0:
        # Minor: 1) last bugfix of previous minor vs target, 2) previous minor base vs that bugfix
        last_prev_minor_bugfix = latest_before(lambda vi: vi.major == major and vi.minor == (minor - 1))
        prev_minor_base = find_tag(major, minor - 1, 0)
        if last_prev_minor_bugfix:
            comparisons.append((last_prev_minor_bugfix, target_version))
        if prev_minor_base and last_prev_minor_bugfix and prev_minor_base != last_prev_minor_bugfix:
            comparisons.append((prev_minor_base, last_prev_minor_bugfix))
    else:
        # Major: 1) last bugfix of previous major vs target,
        #        2) highest minor base of previous major vs that bugfix,
        #        3) previous major base vs that minor base
        last_prev_major_bugfix = latest_before(lambda vi: vi.major == (major - 1)) if major > 0 else None
        # Highest minor base in previous major (v{major-1}.{maxMinor}.0)
        prev_major_minor_bases = [
            (vi, tag) for vi, tag in semver_sorted if major > 0 and vi.major == (major - 1) and vi.patch == 0
        ]
        prev_major_minor_base = prev_major_minor_bases[-1][1] if prev_major_minor_bases else None
        prev_major_base = find_tag(major - 1, 0, 0) if major > 0 else None

        if last_prev_major_bugfix:
            comparisons.append((last_prev_major_bugfix, target_version))
        if prev_major_minor_base and last_prev_major_bugfix and prev_major_minor_base != last_prev_major_bugfix:
            comparisons.append((prev_major_minor_base, last_prev_major_bugfix))
        if prev_major_base and prev_major_minor_base and prev_major_base != prev_major_minor_base:
            comparisons.append((prev_major_base, prev_major_minor_base))

    if not comparisons:
        # Irregular history (e.g. a skipped minor version): compare against the latest preceding release.
        logging.getLogger(__name__).info(
            "No regular predecessor of %s found, comparing against latest preceding tag %s", target_version, latest_any
        )
        comparisons.append((latest_any, target_version))
    return comparisons


def comparison_title(base: Optional[str], head: str) -> str:
    if base is None:
        return f"Changes for {head} (initial release)"
    return f"Changes for {base}..{head}"


def build_llm_files_list(context_dir: str) -> List[str]:
    files = []
    for name in ("commits.log", "public_api.diff"):
        path = os.path.join(context_dir, name)
        if os.path.isfile(path):
            files.append(path)
    pr_dir = os.path.join(context_dir, "pr_discussions")
    if os.path.isdir(pr_dir):
        for entry in sorted(os.listdir(pr_dir)):
            files.append(os.path.join(pr_dir, entry))
    path = os.path.join(context_dir, CODE_DIFF)
    if os.path.isfile(path):
        files.append(path)
    return files


def file_header(name: str) -> str:
    return f"\n===== FILE: {name} =====\n"


def build_llm_message(prompt: str, sections: List[Tuple[str, str]], cut_notes: List[str]) -> str:
    """Assemble the single user message: context files first, instructions last."""
    parts = ["The following files describe the changes in a software project.\n"]
    if cut_notes:
        parts.append(
            "Some of the context was shortened to fit the model context window "
            "(omitted parts are marked in the text): " + "; ".join(cut_notes)[:MAX_NOTES_CHARS] + ".\n"
        )
    for name, content in sections:
        parts.append(file_header(name))
        parts.append(content)
    parts.append("\n===== INSTRUCTIONS =====\n")
    parts.append(prompt)
    return "".join(parts)


def synthesize_notes_for_range(
    repo_url: str,
    base: Optional[str],
    head: str,
    config: ReleaseNotesConfig,
    temp_output_dir: str,
) -> str:
    """Generate release notes for base..head (base None = first release)."""
    log = logging.getLogger(__name__)
    config.validate_for_synthesis()
    # choose prompt (before the expensive context generation, so that invalid versions fail fast)
    change_type = determine_change_type(head, initial=base is None)
    base_prompt = config.prompts.get(config.project_type, {}).get(change_type) or config.prompts["library"][change_type]
    if config.project_prompt:
        prompt = base_prompt + "\n\nProject specific instructions:\n" + config.project_prompt
    else:
        prompt = base_prompt

    log.info("Generating context for %s", comparison_title(base, head))
    generate_diff_context(
        repo_url,
        base,
        head,
        temp_output_dir,
        public_api_command=config.public_api_command,
        diff_exclude_paths=config.diff_exclude_paths,
    )

    files = build_llm_files_list(temp_output_dir)
    sections = []
    for path in files:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            sections.append((os.path.basename(path), f.read()))

    # Everything except the file contents themselves counts against the budget too.
    overhead = len(build_llm_message(prompt, [(name, "") for name, _ in sections], ["x" * MAX_NOTES_CHARS]))
    input_tokens = config.max_context_tokens - config.reserved_output_tokens
    budget_chars = tokens_to_chars(input_tokens) - overhead
    if budget_chars <= 0:
        raise ConfigError(
            f"The prompt alone does not fit into max_context_tokens={config.max_context_tokens} "
            f"(with reserved_output_tokens={config.reserved_output_tokens})"
        )

    def compact_diff() -> str:
        return diff_between(clone_or_fetch(repo_url), base, head, config.diff_exclude_paths, compact=True)

    sections, cut_notes = fit_context(sections, CODE_DIFF, budget_chars, compact_diff)
    for note in cut_notes:
        log.warning("Context too large for the model: %s", note)

    message = build_llm_message(prompt, sections, cut_notes)
    log.info("Calling LLM with %d context file(s): %s", len(sections), [name for name, _ in sections])
    return generate_text(
        message,
        model=config.model,
        api_key_env=config.api_key_env,
        base_url=config.base_url,
        estimated_tokens=estimate_tokens(message),
    )
