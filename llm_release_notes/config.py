import os
import re
from dataclasses import dataclass
from typing import Dict, Optional

import yaml


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
        ),
        "minor_change": (
            "You are an expert technical writer. Based on the provided context (code diff, commit logs, PR discussions, and API diff), "
            "generate release notes for this new version of a library. Make sure to include all API-breaking changes, deprecations and especially new features."
            "Do not focus too much on bug fixes or other minor changes."
            "Never mention the actual version number or type of release in the output. Do not write any introductory paragraphs, just list/describe changes directly."
            "Your tone should be professional and informative, even formal. Avoid expressing emotions, like excitement, or call to action statements (like 'update to new version today to get these features')."
            "Feel free to use emojis and make references to methods and classes in the codebase, but do not give code examples."
            "Structure your summary into sections (in this order) titled 'API-breaking changes', 'New features', and 'Other significant changes'. Omit empty sections."
        ),
        "bugfix": (
            "You are an expert technical writer. Based on the provided context (code diff, commit logs, PR discussions, and API diff), "
            "generate release notes for this new version of a library. Make sure to include all API-breaking changes, deprecations or significant new features."
            "Focus also on bug fixes and all other minor changes."
            "Never mention the actual version number or type of release in the output. Do not write any introductory paragraphs, just list/describe changes directly."
            "Your tone should be professional and informative, even formal. Avoid expressing emotions, like excitement, or call to action statements (like 'update to new version today to get these features')."
            "Feel free to use emojis and make references to methods and classes in the codebase, but do not give code examples."
            "Structure your summary into sections (in this order) titled 'API-breaking changes', 'New features', 'Bug fixes' and 'Other changes'. Omit empty sections."
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
        ),
        "minor_change": (
            "You are an expert technical writer. Based on the provided context (code diff, commit logs, PR discussions, and API diff), "
            "generate release notes for this new version of an application. Make sure to include all breaking changes, deprecations or significant new features."
            "Do not focus too much on bug fixes or other minor changes."
            "Never mention the actual version number or type of release in the output. Do not write any introductory paragraphs, just list/describe changes directly."
            "Your tone should be professional and informative, even formal. Avoid expressing emotions, like excitement, or call to action statements (like 'update to new version today to get these features')."
            "Feel free to use emojis or nice formatting features, but do not talk about code changes, methods, or classes in the codebase; focus on user-facing features."
            "Structure your summary into sections (in this order) titled 'API-breaking changes', 'New features', 'Bug fixes' and 'Other changes'. Omit empty sections."
        ),
        "bugfix": (
            "You are an expert technical writer. Based on the provided context (code diff, commit logs, PR discussions, and API diff), "
            "generate release notes for this new version of an application. Make sure to include all breaking changes, deprecations or significant new features."
            "Focus also on bug fixes and all other minor changes."
            "Never mention the actual version number or type of release in the output. Do not write any introductory paragraphs, just list/describe changes directly."
            "Your tone should be professional and informative, even formal. Avoid expressing emotions, like excitement, or call to action statements (like 'update to new version today to get these features')."
            "Feel free to use emojis or nice formatting features, but do not talk about code changes, methods, or classes in the codebase; focus on user-facing features."
            "Structure your summary into sections (in this order) titled 'API-breaking changes', 'New features', 'Bug fixes' and 'Other changes'. Omit empty sections."
        ),
    },
}


@dataclass
class ReleaseNotesConfig:
    project_type: str = "library"
    public_api_command: Optional[str] = None
    prompts: Dict[str, Dict[str, str]] = None
    model_name: str = "gemini-2.5-flash"
    project_prompt: Optional[str] = None

    @staticmethod
    def load(config_path: Optional[str], repo_root: Optional[str]) -> "ReleaseNotesConfig":
        path = config_path
        if path is None and repo_root is not None:
            candidate = os.path.join(repo_root, ".releasenotes.yml")
            if os.path.isfile(candidate):
                path = candidate
        if path is None or not os.path.isfile(path):
            return ReleaseNotesConfig(project_type="library", public_api_command=None, prompts=DEFAULT_PROMPTS, model_name="gemini-2.5-flash", project_prompt=None)
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        project_type = data.get("project_type", "library")
        public_api_command = data.get("public_api_command")
        model_name = data.get("gemini_model", "gemini-2.5-flash")
        project_prompt = data.get("project_prompt")
        prompts = DEFAULT_PROMPTS.copy()
        user_prompts = data.get("prompts") or {}
        for domain, entries in user_prompts.items():
            if domain not in prompts:
                prompts[domain] = {}
            for k, v in (entries or {}).items():
                prompts[domain][k] = v
        return ReleaseNotesConfig(project_type=project_type, public_api_command=public_api_command, prompts=prompts, model_name=model_name, project_prompt=project_prompt)


SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def parse_semver_tag(tag: str) -> Optional[tuple[int, int, int]]:
    m = SEMVER_RE.match(tag)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


