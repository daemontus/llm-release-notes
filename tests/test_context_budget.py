"""Tests for the context_budget module."""

from llm_release_notes.context_budget import allocate, fit_context, fit_diff, split_diff_by_file, truncate_text


def file_diff(path: str, body_len: int) -> str:
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n" + "+" * body_len + "\n"


def test_allocate():
    assert allocate([10, 20, 30], 100) == [10, 20, 30]
    assert allocate([10, 100, 100], 110) == [10, 50, 50]
    assert allocate([], 10) == []


def test_truncate_text():
    assert truncate_text("short", 100) == "short"
    cut = truncate_text("x" * 1000, 200)
    assert len(cut) <= 200
    assert "truncated" in cut


def test_split_diff_by_file():
    diff = file_diff("a.txt", 5) + file_diff("dir/b.txt", 5)
    assert [path for path, _ in split_diff_by_file(diff)] == ["a.txt", "dir/b.txt"]
    assert "".join(chunk for _, chunk in split_diff_by_file(diff)) == diff


def test_fit_diff_omits_whole_files():
    diff = file_diff("small.txt", 10) + file_diff("huge.lock", 10_000) + file_diff("other.txt", 10)
    fitted = fit_diff(diff, 1000)
    assert len(fitted) <= 1000
    assert "diff --git a/small.txt" in fitted
    assert "diff --git a/other.txt" in fitted
    assert "diff --git a/huge.lock" not in fitted
    assert "- huge.lock" in fitted


def test_fit_context_fits_unchanged():
    sections = [("commits.log", "abc"), ("code.diff", file_diff("a", 10))]
    assert fit_context(sections, "code.diff", 10_000) == (sections, [])


def test_fit_context_prefers_compact_diff():
    full = file_diff("a.txt", 2000)
    compact = file_diff("a.txt", 500)
    sections = [("commits.log", "abc"), ("code.diff", full)]
    fitted, notes = fit_context(sections, "code.diff", 1000, compact_diff=lambda: compact)
    assert dict(fitted)["code.diff"] == compact
    assert dict(fitted)["commits.log"] == "abc"
    assert notes


def test_fit_context_limits_aux_sections():
    sections = [("commits.log", "c" * 5000), ("PR-1.txt", "p" * 100), ("code.diff", file_diff("a.txt", 5000))]
    fitted, notes = fit_context(sections, "code.diff", 4000)
    assert [name for name, _ in fitted] == ["commits.log", "PR-1.txt", "code.diff"]
    assert sum(len(content) for _, content in fitted) <= 4000
    assert dict(fitted)["PR-1.txt"] == "p" * 100
    assert len(dict(fitted)["commits.log"]) <= 2000
