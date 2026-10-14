"""Configuration loading and default prompts for the Release Notes tool."""

import copy
import os
import re
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, List

import yaml

from .exceptions import ConfigError


# Default prompt templates used when user configuration does not override them
DEFAULT_PROMPTS = {
    "library": {
        # These prompts mainly differ in the specifics of what the model should focus on, but are otherwise the same in terms of tone/general instructions.
        "major_change": (
            "You are an expert technical writer. Based on the provided context (code diff, commit logs, PR discussions, and API diff), "
            "generate release notes for this new version of a library. Make sure to include all API-breaking changes, deprecations or significant new features. "
            "Do not focus too much on bug fixes or minor changes. "
            "Never mention the actual version number or type of release in the output. Do not write any introductory paragraphs, just list/describe changes directly. "
            "Your tone should be professional and informative, even formal. Avoid expressing emotions, like excitement, or call to action statements (like 'update to new version today to get these features'). "
            "Feel free to use emojis and make references to methods and classes in the codebase, but do not give code examples. "
            "Structure your summary into sections (in this order) titled 'API-breaking changes', 'New features', and 'Other significant changes'. Omit empty sections. "
            "If the commits or pull requests resolve specific issues, you can link these issues in the release notes (e.g. Issue #5) "
        ),
        "minor_change": (
            "You are an expert technical writer. Based on the provided context (code diff, commit logs, PR discussions, and API diff), "
            "generate release notes for this new version of a library. Make sure to include all API-breaking changes, deprecations and especially new features. "
            "Do not focus too much on bug fixes or other minor changes. "
            "Never mention the actual version number or type of release in the output. Do not write any introductory paragraphs, just list/describe changes directly. "
            "Your tone should be professional and informative, even formal. Avoid expressing emotions, like excitement, or call to action statements (like 'update to new version today to get these features'). "
            "Feel free to use emojis and make references to methods and classes in the codebase, but do not give code examples. "
            "Structure your summary into sections (in this order) titled 'API-breaking changes', 'New features', and 'Other significant changes'. Omit empty sections. "
            "If the commits or pull requests resolve specific issues, you can link these issues in the release notes (e.g. Issue #5) "
        ),
        "bugfix": (
            "You are an expert technical writer. Based on the provided context (code diff, commit logs, PR discussions, and API diff), "
            "generate release notes for this new version of a library. Make sure to include all API-breaking changes, deprecations or significant new features. "
            "Focus also on bug fixes and all other minor changes. "
            "Never mention the actual version number or type of release in the output. Do not write any introductory paragraphs, just list/describe changes directly. "
            "Your tone should be professional and informative, even formal. Avoid expressing emotions, like excitement, or call to action statements (like 'update to new version today to get these features'). "
            "Feel free to use emojis and make references to methods and classes in the codebase, but do not give code examples. "
            "Structure your summary into sections (in this order) titled 'API-breaking changes', 'New features', 'Bug fixes' and 'Other changes'. Omit empty sections. "
            "If the commits or pull requests resolve specific issues, you can link these issues in the release notes (e.g. Issue #5) "
        ),
    },
    "application": {
        "major_change": (
            "You are an expert technical writer. Based on the provided context (code diff, commit logs, PR discussions, and API diff), "
            "generate release notes for this new version of an application. Make sure to include all breaking changes, deprecations or significant new features. "
            "Do not focus too much on bug fixes or minor changes. "
            "Never mention the actual version number or type of release in the output. Do not write any introductory paragraphs, just list/describe changes directly. "
            "Your tone should be professional and informative, even formal. Avoid expressing emotions, like excitement, or call to action statements (like 'update to new version today to get these features'). "
            "Feel free to use emojis or nice formatting features, but do not talk about code changes, methods, or classes in the codebase; focus on user-facing features. "
            "Structure your summary into sections (in this order) titled 'API-breaking changes', 'New features', 'Bug fixes' and 'Other changes'. Omit empty sections. "
            "If the commits or pull requests resolve specific issues, you can link these issues in the release notes (e.g. Issue #5) "
        ),
        "minor_change": (
            "You are an expert technical writer. Based on the provided context (code diff, commit logs, PR discussions, and API diff), "
            "generate release notes for this new version of an application. Make sure to include all breaking changes, deprecations or significant new features. "
            "Do not focus too much on bug fixes or other minor changes. "
            "Never mention the actual version number or type of release in the output. Do not write any introductory paragraphs, just list/describe changes directly. "
            "Your tone should be professional and informative, even formal. Avoid expressing emotions, like excitement, or call to action statements (like 'update to new version today to get these features'). "
            "Feel free to use emojis or nice formatting features, but do not talk about code changes, methods, or classes in the codebase; focus on user-facing features. "
            "Structure your summary into sections (in this order) titled 'API-breaking changes', 'New features', 'Bug fixes' and 'Other changes'. Omit empty sections. "
            "If the commits or pull requests resolve specific issues, you can link these issues in the release notes (e.g. Issue #5) "
        ),
        "bugfix": (
            "You are an expert technical writer. Based on the provided context (code diff, commit logs, PR discussions, and API diff), "
            "generate release notes for this new version of an application. Make sure to include all breaking changes, deprecations or significant new features. "
            "Focus also on bug fixes and all other minor changes. "
            "Never mention the actual version number or type of release in the output. Do not write any introductory paragraphs, just list/describe changes directly. "
            "Your tone should be professional and informative, even formal. Avoid expressing emotions, like excitement, or call to action statements (like 'update to new version today to get these features'). "
            "Feel free to use emojis or nice formatting features, but do not talk about code changes, methods, or classes in the codebase; focus on user-facing features. "
            "Structure your summary into sections (in this order) titled 'API-breaking changes', 'New features', 'Bug fixes' and 'Other changes'. Omit empty sections. "
            "If the commits or pull requests resolve specific issues, you can link these issues in the release notes (e.g. Issue #5) "
        ),
    },
}


# Prompts for the first release of a project (compared against an empty repository).
INITIAL_RELEASE_PROMPTS = {
    "library": (
        "You are an expert technical writer. Based on the provided context (the full code of the project as a diff against an empty repository, commit logs, PR discussions, and public API), "
        "generate release notes for the first release of a library. Describe the main features and the most important parts of the public API. "
        "Do not describe the development history, individual commits, or bug fixes made before this release. "
        "Never mention the actual version number or type of release in the output. Do not write any introductory paragraphs, just describe the library directly. "
        "Your tone should be professional and informative, even formal. Avoid expressing emotions, like excitement, or call to action statements (like 'try the new library today'). "
        "Feel free to use emojis and make references to methods and classes in the codebase, but do not give code examples. "
        "Structure your summary into sections (in this order) titled 'Main features' and 'Other notable aspects'. Omit empty sections. "
    ),
    "application": (
        "You are an expert technical writer. Based on the provided context (the full code of the project as a diff against an empty repository, commit logs, PR discussions, and public API), "
        "generate release notes for the first release of an application. Describe the main user-facing features. "
        "Do not describe the development history, individual commits, or bug fixes made before this release. "
        "Never mention the actual version number or type of release in the output. Do not write any introductory paragraphs, just describe the application directly. "
        "Your tone should be professional and informative, even formal. Avoid expressing emotions, like excitement, or call to action statements (like 'try the new application today'). "
        "Feel free to use emojis or nice formatting features, but do not talk about code changes, methods, or classes in the codebase; focus on user-facing features. "
        "Structure your summary into sections (in this order) titled 'Main features' and 'Other notable aspects'. Omit empty sections. "
    ),
}
for _domain, _prompt in INITIAL_RELEASE_PROMPTS.items():
    DEFAULT_PROMPTS[_domain]["initial_release"] = _prompt


DEFAULT_API_KEY_ENV = "LLM_API_KEY"
DEFAULT_RESERVED_OUTPUT_TOKENS = 8192


@dataclass
class ReleaseNotesConfig:
    """Strongly-typed configuration for release notes generation.

    Attributes:
        project_type: Either "library" or "application"; selects prompt family.
        public_api_command: Optional shell command to print public API.
        prompts: Mapping of prompt families and change types to templates.
        model: Model name passed to the OpenAI-compatible endpoint (required for synthesis).
        base_url: Base URL of the OpenAI-compatible endpoint (None = OpenAI default).
        api_key_env: Name of the environment variable holding the API key.
        max_context_tokens: Context window of the model in tokens (required for synthesis).
        reserved_output_tokens: Part of the context window kept free for the generated notes.
        project_prompt: Project-wide additional instructions appended to prompts.
        diff_exclude_paths: Git pathspecs excluded from the code diff.
    """
    project_type: str = "library"
    public_api_command: Optional[str] = None
    prompts: Dict[str, Dict[str, str]] = field(default_factory=lambda: copy.deepcopy(DEFAULT_PROMPTS))
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key_env: str = DEFAULT_API_KEY_ENV
    max_context_tokens: Optional[int] = None
    reserved_output_tokens: int = DEFAULT_RESERVED_OUTPUT_TOKENS
    project_prompt: Optional[str] = None
    diff_exclude_paths: Optional[List[str]] = None

    @staticmethod
    def load(config_path: Optional[str], repo_root: Optional[str]) -> "ReleaseNotesConfig":
        """Load configuration from a YAML file.

        Resolution order:
        - If config_path is provided, load it (it must exist).
        - Else, if repo_root/.releasenotes.yml exists, load it.
        - Else, return defaults.
        """
        if config_path is not None and not os.path.isfile(config_path):
            raise ConfigError(f"Config file not found: {config_path}")
        path = config_path
        if path is None and repo_root is not None:
            candidate = os.path.join(repo_root, ".releasenotes.yml")
            if os.path.isfile(candidate):
                path = candidate
        if path is None:
            logging.getLogger(__name__).info("Config not provided, using defaults")
            return ReleaseNotesConfig()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except (IOError, yaml.YAMLError) as e:
            raise ConfigError(f"Error loading config file from {path}: {e}") from e
        if not isinstance(data, dict):
            raise ConfigError(f"Config file {path} must contain a YAML mapping")
        if "gemini_model" in data:
            raise ConfigError(
                f"Config key 'gemini_model' in {path} is no longer supported; use 'model' together with "
                "'base_url' and 'max_context_tokens' to configure an OpenAI-compatible endpoint"
            )
        prompts = copy.deepcopy(DEFAULT_PROMPTS)
        user_prompts = data.get("prompts") or {}
        for domain, entries in user_prompts.items():
            if domain not in prompts:
                prompts[domain] = {}
            for k, v in (entries or {}).items():
                prompts[domain][k] = v
        cfg = ReleaseNotesConfig(
            project_type=data.get("project_type", "library"),
            public_api_command=data.get("public_api_command"),
            prompts=prompts,
            model=data.get("model"),
            base_url=data.get("base_url"),
            api_key_env=data.get("api_key_env") or DEFAULT_API_KEY_ENV,
            max_context_tokens=_optional_int(data, "max_context_tokens", path),
            reserved_output_tokens=_optional_int(data, "reserved_output_tokens", path) or DEFAULT_RESERVED_OUTPUT_TOKENS,
            project_prompt=data.get("project_prompt"),
            diff_exclude_paths=data.get("diff_exclude_paths") or None,
        )
        logging.getLogger(__name__).info(
            "Loaded config: project_type=%s, model=%s, base_url=%s, max_context_tokens=%s, public_api_command=%s, project_prompt_len=%s, diff_excludes=%s",
            cfg.project_type,
            cfg.model,
            cfg.base_url or "default",
            cfg.max_context_tokens,
            "yes" if bool(cfg.public_api_command) else "no",
            len(cfg.project_prompt) if cfg.project_prompt else 0,
            len(cfg.diff_exclude_paths) if cfg.diff_exclude_paths else 0,
        )
        return cfg

    def validate_for_synthesis(self) -> None:
        """Check that all settings needed to call the model are present."""
        if not self.model:
            raise ConfigError("No model configured; set 'model' in the config file or use --model")
        if not self.max_context_tokens:
            raise ConfigError(
                "No context length configured; set 'max_context_tokens' in the config file or use --max-context-tokens"
            )
        if self.max_context_tokens <= self.reserved_output_tokens:
            raise ConfigError(
                f"max_context_tokens ({self.max_context_tokens}) must be larger than "
                f"reserved_output_tokens ({self.reserved_output_tokens})"
            )


def _optional_int(data: dict, key: str, path: str) -> Optional[int]:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"Config key '{key}' in {path} must be a positive integer, got {value!r}")
    return value


SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def parse_semver_tag(tag: str) -> Optional[tuple[int, int, int]]:
    """Parse tags like 'vX.Y.Z' or 'X.Y.Z' into numeric tuple.

    Returns None if the tag doesn't match SemVer pattern.
    """
    m = SEMVER_RE.match(tag)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


