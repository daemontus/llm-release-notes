"""Fitting the diff context into the context window of the model.

OpenAI-compatible endpoints offer no portable way to count tokens before sending
a request, so we work with a conservative character-based estimate instead.
"""

import math
import re
from typing import Callable, List, Optional, Tuple

# Code and diffs typically use 3.5-4 characters per token; assuming 3 leaves a safety margin.
CHARS_PER_TOKEN = 3.0

# Share of the input budget that non-diff context (commits, PRs, API diff) may take
# when everything does not fit. The code diff gets the rest.
MAX_AUX_SHARE = 0.5

DIFF_FILE_RE = re.compile(r"^diff --git a/(.*?) b/", re.MULTILINE)


def estimate_tokens(text: str) -> int:
    """Conservative (over-)estimate of the number of tokens in text."""
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def tokens_to_chars(tokens: int) -> int:
    return int(tokens * CHARS_PER_TOKEN)


def truncate_text(text: str, max_chars: int) -> str:
    """Cut text to at most max_chars, marking the omitted part."""
    if len(text) <= max_chars:
        return text
    marker = "\n[... truncated: {} characters omitted to fit the model context ...]\n"
    keep = max(0, max_chars - len(marker.format(len(text))))
    return text[:keep] + marker.format(len(text) - keep)


def allocate(sizes: List[int], budget: int) -> List[int]:
    """Split budget between items of the given sizes ("water-filling").

    Items smaller than their fair share keep their full size and the
    remainder is split evenly between the larger items.
    """
    caps = [0] * len(sizes)
    remaining = budget
    pending = sorted(range(len(sizes)), key=lambda i: sizes[i])
    while pending:
        share = remaining // len(pending)
        i = pending[0]
        if sizes[i] <= share:
            caps[i] = sizes[i]
            remaining -= sizes[i]
            pending.pop(0)
        else:
            for j in pending:
                caps[j] = share
            break
    return caps


def split_diff_by_file(diff: str) -> List[Tuple[str, str]]:
    """Split a git diff into (path, chunk) pairs, one per changed file."""
    starts = [m.start() for m in DIFF_FILE_RE.finditer(diff)]
    if not starts:
        return [("", diff)] if diff else []
    chunks = []
    if starts[0] > 0:
        chunks.append(("", diff[: starts[0]]))
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(diff)
        chunk = diff[start:end]
        m = DIFF_FILE_RE.match(chunk)
        chunks.append((m.group(1) if m else "", chunk))
    return chunks


def fit_diff(diff: str, max_chars: int) -> str:
    """Fit a diff into max_chars by omitting whole files.

    Files are kept in their original order; a file that does not fit is skipped
    (smaller files after it may still fit). Omitted files are listed at the end,
    so that the model at least knows they were changed.
    """
    if len(diff) <= max_chars:
        return diff
    chunks = split_diff_by_file(diff)
    # Reserve room for the list of omitted files (bounded, so that it cannot eat the whole budget).
    reserve = min(sum(len(path) + 3 for path, _ in chunks) + 200, max_chars // 5)
    available = max_chars - reserve
    kept: List[str] = []
    omitted: List[str] = []
    for path, chunk in chunks:
        if len(chunk) <= available:
            kept.append(chunk)
            available -= len(chunk)
        else:
            omitted.append(path or "(diff header)")
    note = "\n[... the diff of the following files was omitted to fit the model context: ...]\n"
    listed = ""
    for i, path in enumerate(omitted):
        line = f"- {path}\n"
        if len(note) + len(listed) + len(line) + 40 > reserve:
            listed += f"- ... and {len(omitted) - i} more file(s)\n"
            break
        listed += line
    return "".join(kept) + note + listed


def fit_context(
    sections: List[Tuple[str, str]],
    diff_name: str,
    budget_chars: int,
    compact_diff: Optional[Callable[[], str]] = None,
) -> Tuple[List[Tuple[str, str]], List[str]]:
    """Fit named context sections into budget_chars.

    The section called diff_name is treated as a git diff: if the context does not
    fit, it is first replaced by compact_diff() (no context lines), and then fitted
    file-by-file. Other sections get at most MAX_AUX_SHARE of the budget and are
    truncated evenly if they exceed it.

    Returns the fitted sections and a list of human-readable notes on what was cut.
    """
    notes: List[str] = []
    total = sum(len(content) for _, content in sections)
    if total <= budget_chars:
        return sections, notes

    diff = next((content for name, content in sections if name == diff_name), "")
    aux = [(name, content) for name, content in sections if name != diff_name]

    if compact_diff is not None and diff:
        compact = compact_diff()
        if len(compact) < len(diff):
            notes.append("code diff reduced to compact form (no context lines)")
            diff = compact

    aux_sizes = [len(content) for _, content in aux]
    aux_total = sum(aux_sizes)
    aux_budget = max(int(budget_chars * MAX_AUX_SHARE), budget_chars - len(diff))
    if aux_total > aux_budget:
        caps = allocate(aux_sizes, aux_budget)
        for (name, content), cap in zip(aux, caps):
            if len(content) > cap:
                notes.append(f"{name} truncated to {cap} of {len(content)} characters")
        aux = [(name, truncate_text(content, cap)) for (name, content), cap in zip(aux, caps)]
        aux_total = sum(len(content) for _, content in aux)

    diff_budget = budget_chars - aux_total
    if len(diff) > diff_budget:
        notes.append(f"code diff reduced from {len(diff)} to at most {diff_budget} characters by omitting files")
        diff = fit_diff(diff, diff_budget)

    fitted = []
    for name, content in sections:
        if name == diff_name:
            fitted.append((name, diff))
        else:
            fitted.append(next(item for item in aux if item[0] == name))
    return fitted, notes
