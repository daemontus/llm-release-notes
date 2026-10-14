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


def write_config(tmp_path, text):
    path = tmp_path / "cfg.yml"
    path.write_text(text)
    return str(path)


def test_load_openai_settings(tmp_path):
    from llm_release_notes.config import ReleaseNotesConfig

    path = write_config(
        tmp_path,
        "model: some/model\nbase_url: https://example.com/v1\nmax_context_tokens: 100000\n"
        "prompts:\n  library:\n    bugfix: custom\n",
    )
    cfg = ReleaseNotesConfig.load(path, None)
    assert cfg.model == "some/model"
    assert cfg.base_url == "https://example.com/v1"
    assert cfg.max_context_tokens == 100000
    assert cfg.prompts["library"]["bugfix"] == "custom"
    cfg.validate_for_synthesis()
    # Defaults must not be modified by user prompts.
    assert ReleaseNotesConfig().prompts["library"]["bugfix"] != "custom"


@pytest.mark.parametrize(
    "text",
    [
        "max_context_tokens: 100000\n",  # no model
        "model: m\n",  # no context length
        "model: m\nmax_context_tokens: 1000\n",  # smaller than reserved output
    ],
)
def test_validate_for_synthesis_rejects_incomplete(tmp_path, text):
    from llm_release_notes.config import ReleaseNotesConfig
    from llm_release_notes.exceptions import ConfigError

    cfg = ReleaseNotesConfig.load(write_config(tmp_path, text), None)
    with pytest.raises(ConfigError):
        cfg.validate_for_synthesis()


@pytest.mark.parametrize("text", ["gemini_model: gemini-2.5-flash\n", "max_context_tokens: lots\n"])
def test_load_rejects_invalid(tmp_path, text):
    from llm_release_notes.config import ReleaseNotesConfig
    from llm_release_notes.exceptions import ConfigError

    with pytest.raises(ConfigError):
        ReleaseNotesConfig.load(write_config(tmp_path, text), None)
