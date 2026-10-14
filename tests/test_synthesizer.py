"""Tests for the synthesizer module."""

import pytest

from llm_release_notes.exceptions import llmReleaseNotesError
from llm_release_notes.synthesizer import comparison_title, determine_change_type, select_comparisons_single_version

TAGS = ["v1.0.0", "v1.0.1", "v1.1.0", "v1.1.2", "v2.0.0", "not-a-version"]


@pytest.mark.parametrize(
    "version, tags, expected",
    [
        # bugfix
        ("v1.1.2", TAGS, [("v1.1.0", "v1.1.2")]),
        # minor
        ("v1.1.0", TAGS, [("v1.0.1", "v1.1.0"), ("v1.0.0", "v1.0.1")]),
        # major
        ("v2.0.0", TAGS, [("v1.1.2", "v2.0.0"), ("v1.1.0", "v1.1.2"), ("v1.0.0", "v1.1.0")]),
        # tags without the 'v' prefix
        ("1.1.0", ["1.0.0", "1.0.3", "1.1.0"], [("1.0.3", "1.1.0"), ("1.0.0", "1.0.3")]),
        # first release (no earlier SemVer tags)
        ("v0.1.0", ["v0.1.0", "nightly"], [(None, "v0.1.0")]),
        ("v1.0.0", [], [(None, "v1.0.0")]),
        ("v0.0.1", ["v0.0.1", "v0.0.2"], [(None, "v0.0.1")]),
        # skipped minor version falls back to the latest preceding tag
        ("v1.3.0", ["v1.1.0", "v1.1.4", "v1.3.0"], [("v1.1.4", "v1.3.0")]),
        # bugfix without an earlier release on the same minor branch
        ("v1.2.1", ["v1.1.0", "v1.2.1"], [("v1.1.0", "v1.2.1")]),
    ],
)
def test_select_comparisons_single_version(version, tags, expected):
    assert select_comparisons_single_version(version, tags) == expected


def test_select_comparisons_rejects_non_semver():
    with pytest.raises(llmReleaseNotesError):
        select_comparisons_single_version("release-1", TAGS)


@pytest.mark.parametrize(
    "version, initial, expected",
    [
        ("v1.2.3", False, "bugfix"),
        ("v1.2.0", False, "minor_change"),
        ("v2.0.0", False, "major_change"),
        ("v2.0.0", True, "initial_release"),
    ],
)
def test_determine_change_type(version, initial, expected):
    assert determine_change_type(version, initial) == expected


def test_comparison_title():
    assert comparison_title("v1.1.0", "v1.1.5") == "Changes for v1.1.0..v1.1.5"
    assert comparison_title(None, "v1.0.0") == "Changes for v1.0.0 (initial release)"
