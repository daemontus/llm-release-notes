"""Tests for the config module."""

import pytest

from llm_release_notes.config import parse_semver_tag


@pytest.mark.parametrize(
    "tag, expected",
    [
        ("v1.2.3", (1, 2, 3)),
        ("1.2.3", (1, 2, 3)),
        ("v0.1.0", (0, 1, 0)),
        ("v10.20.30", (10, 20, 30)),
        ("1.2.3-alpha", None),
        ("1.2", None),
        ("v1.2", None),
        ("abc", None),
    ],
)
def test_parse_semver_tag(tag, expected):
    assert parse_semver_tag(tag) == expected
