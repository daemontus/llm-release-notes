"""Tests for the github_api module."""

import pytest

from llm_release_notes.github_api import parse_owner_repo_from_url


@pytest.mark.parametrize(
    "url, expected",
    [
        ("git@github.com:owner/repo.git", ("owner", "repo")),
        ("https://github.com/owner/repo", ("owner", "repo")),
        ("https://github.com/owner/repo.git", ("owner", "repo")),
        ("git@gitlab.com:owner/repo.git", None),
        ("https://example.com/owner/repo", None),
    ],
)
def test_parse_owner_repo_from_url(url, expected):
    assert parse_owner_repo_from_url(url) == expected
