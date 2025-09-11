"""Tests for the diff_context module."""

import pytest

from llm_release_notes.diff_context import extract_pr_numbers


@pytest.mark.parametrize(
    "commit_message, expected",
    [
        ("feat: new feature (#123)", [123]),
        ("Merge pull request #456 from some/branch", [456]),
        ("fix: bug fix, pr #789", [789]),
        ("docs: update README", []),
        ("Merge pull request #123\n\nfeat: new feature (#456)", [123, 456]),
    ],
)
def test_extract_pr_numbers(commit_message, expected):
    assert sorted(extract_pr_numbers(commit_message)) == sorted(expected)

