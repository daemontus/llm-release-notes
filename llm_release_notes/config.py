"""Configuration loading and default prompts for the Release Notes tool."""

import os
import re
import logging
from dataclasses import dataclass
from typing import Dict, Optional, List

import yaml


# Default prompt templates used when user configuration does not override them
DEFAULT_PROMPTS = {
    "library": {
        # These prompts mainly differ in the specifics of what the model should focus on, but are otherwise the same in terms of tone/general instructions.
        "major_change": (
            "You are an expert technical writer. Based on the provided context (code diff, commit logs, PR discussions, and API diff), "
            "generate release notes for this new version of a library. Make sure to include all API-breaking changes, deprecations or significant new features."
            "Do not focus too much on bug fixes or minor changes."
            "Never mention the actual version number or type of release in the output. Do not write any introductory paragraphs, just list/describe changes directly."
            "Your tone should be professional and informative, even formal. Avoid expressing emotions, like excitement, or call to action statements (like 'update to new version today to get these features')."
            "Feel free to use emojis and make references to methods and classes in the codebase, but do not give code examples."
            "Structure your summary into sections (in this order) titled 'API-breaking changes', 'New features', and 'Other significant changes'. Omit empty sections."
            "If the commits or pull requests resolve specific issues, you can link these issues in the release notes (e.g. Issue #5)"
        ),
        "minor_change": (
            "You are an expert technical writer. Based on the provided context (code diff, commit logs, PR discussions, and API diff), "
            "generate release notes for this new version of a library. Make sure to include all API-breaking changes, deprecations and especially new features."
            "Do not focus too much on bug fixes or other minor changes."
            "Never mention the actual version number or type of release in the output. Do not write any introductory paragraphs, just list/describe changes directly."
            "Your tone should be professional and informative, even formal. Avoid expressing emotions, like excitement, or call to action statements (like 'update to new version today to get these features')."
            "Feel free to use emojis and make references to methods and classes in the codebase, but do not give code examples."
            "Structure your summary into sections (in this order) titled 'API-breaking changes', 'New features', and 'Other significant changes'. Omit empty sections."
            "If the commits or pull requests resolve specific issues, you can link these issues in the release notes (e.g. Issue #5)"
        ),
        "bugfix": (
            "You are an expert technical writer. Based on the provided context (code diff, commit logs, PR discussions, and API diff), "
            "generate release notes for this new version of a library. Make sure to include all API-breaking changes, deprecations or significant new features."
            "Focus also on bug fixes and all other minor changes."
            "Never mention the actual version number or type of release in the output. Do not write any introductory paragraphs, just list/describe changes directly."
            "Your tone should be professional and informative, even formal. Avoid expressing emotions, like excitement, or call to action statements (like 'update to new version today to get these features')."
            "Feel free to use emojis and make references to methods and classes in the codebase, but do not give code examples."
            "Structure your summary into sections (in this order) titled 'API-breaking changes', 'New features', 'Bug fixes' and 'Other changes'. Omit empty sections."
            "If the commits or pull requests resolve specific issues, you can link these issues in the release notes (e.g. Issue #5)"
        ),
    },
    "application": {
        "major_change": (
            "You are an expert technical writer. Based on the provided context (code diff, commit logs, PR discussions, and API diff), "
            "generate release notes for this new version of an application. Make sure to include all breaking changes, deprecations or significant new features."
            "Do not focus too much on bug fixes or minor changes."
            "Never mention the actual version number or type of release in the output. Do not write any introductory paragraphs, just list/describe changes directly."
            "Your tone should be professional and informative, even formal. Avoid expressing emotions, like excitement, or call to action statements (like 'update to new version today to get these features')."
            "Feel free to use emojis or nice formatting features, but do not talk about code changes, methods, or classes in the codebase; focus on user-facing features."
            "Structure your summary into sections (in this order) titled 'API-breaking changes', 'New features', 'Bug fixes' and 'Other changes'. Omit empty sections."
            "If the commits or pull requests resolve specific issues, you can link these issues in the release notes (e.g. Issue #5)"
        ),
        "minor_change": (
            "You are an expert technical writer. Based on the provided context (code diff, commit logs, PR discussions, and API diff), "
            "generate release notes for this new version of an application. Make sure to include all breaking changes, deprecations or significant new features."
            "Do not focus too much on bug fixes or other minor changes."
            "Never mention the actual version number or type of release in the output. Do not write any introductory paragraphs, just list/describe changes directly."
            "Your tone should be professional and informative, even formal. Avoid expressing emotions, like excitement, or call to action statements (like 'update to new version today to get these features')."
            "Feel free to use emojis or nice formatting features, but do not talk about code changes, methods, or classes in the codebase; focus on user-facing features."
            "Structure your summary into sections (in this order) titled 'API-breaking changes', 'New features', 'Bug fixes' and 'Other changes'. Omit empty sections."
            "If the commits or pull requests resolve specific issues, you can link these issues in the release notes (e.g. Issue #5)"
        ),
        "bugfix": (
            "You are an expert technical writer. Based on the provided context (code diff, commit logs, PR discussions, and API diff), "
            "generate release notes for this new version of an application. Make sure to include all breaking changes, deprecations or significant new features."
            "Focus also on bug fixes and all other minor changes."
            "Never mention the actual version number or type of release in the output. Do not write any introductory paragraphs, just list/describe changes directly."
            "Your tone should be professional and informative, even formal. Avoid expressing emotions, like excitement, or call to action statements (like 'update to new version today to get these features')."
            "Feel free to use emojis or nice formatting features, but do not talk about code changes, methods, or classes in the codebase; focus on user-facing features."
            "Structure your summary into sections (in this order) titled 'API-breaking changes', 'New features', 'Bug fixes' and 'Other changes'. Omit empty sections."
            "If the commits or pull requests resolve specific issues, you can link these issues in the release notes (e.g. Issue #5)"
        ),
    },
}


@dataclass
class ReleaseNotesConfig:
    """Strongly-typed configuration for release notes generation.

    Attributes:
        project_type: Either "library" or "application"; selects prompt family.
        public_api_command: Optional shell command to print public API.
        prompts: Mapping of prompt families and change types to templates.
        model_name: Gemini model name to use for generation.
        project_prompt: Project-wide additional instructions appended to prompts.
    """
    project_type: str = "library"
    public_api_command: Optional[str] = None
    prompts: Dict[str, Dict[str, str]] = None
    model_name: str = "gemini-2.5-flash"
    project_prompt: Optional[str] = None
    diff_exclude_paths: Optional[List[str]] = None

    @staticmethod
    def load(config_path: Optional[str], repo_root: Optional[str]) -> "ReleaseNotesConfig":
        """Load configuration from a YAML file.

        Resolution order:
        - If config_path is provided and exists, load it.
        - Else, if repo_root/.releasenotes.yml exists, load it.
        - Else, return defaults.
        """
        path = config_path
        if path is None and repo_root is not None:
            candidate = os.path.join(repo_root, ".releasenotes.yml")
            if os.path.isfile(candidate):
                path = candidate
        if path is None or not os.path.isfile(path):
            logging.getLogger(__name__).info("Config not provided, using defaults")
            return ReleaseNotesConfig(project_type="library", public_api_command=None, prompts=DEFAULT_PROMPTS, model_name="gemini-2.5-flash", project_prompt=None, diff_exclude_paths=None)
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        project_type = data.get("project_type", "library")
        public_api_command = data.get("public_api_command")
        model_name = data.get("gemini_model", "gemini-2.5-flash")
        project_prompt = data.get("project_prompt")
        diff_exclude_paths = data.get("diff_exclude_paths") or None
        prompts = DEFAULT_PROMPTS.copy()
        user_prompts = data.get("prompts") or {}
        for domain, entries in user_prompts.items():
            if domain not in prompts:
                prompts[domain] = {}
            for k, v in (entries or {}).items():
                prompts[domain][k] = v
        log = logging.getLogger(__name__)
        log.info(
            "Loaded config: project_type=%s, model_name=%s, public_api_command=%s, project_prompt_len=%s, diff_excludes=%s",
            project_type,
            model_name,
            "yes" if bool(public_api_command) else "no",
            len(project_prompt) if project_prompt else 0,
            len(diff_exclude_paths) if diff_exclude_paths else 0,
        )
        return ReleaseNotesConfig(project_type=project_type, public_api_command=public_api_command, prompts=prompts, model_name=model_name, project_prompt=project_prompt, diff_exclude_paths=diff_exclude_paths)


SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def parse_semver_tag(tag: str) -> Optional[tuple[int, int, int]]:
    """Parse tags like 'vX.Y.Z' or 'X.Y.Z' into numeric tuple.

    Returns None if the tag doesn't match SemVer pattern.
    """
    m = SEMVER_RE.match(tag)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


