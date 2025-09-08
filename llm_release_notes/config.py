import os
import re
from dataclasses import dataclass
from typing import Dict, Optional

import yaml


DEFAULT_PROMPTS = {
    "library": {
        "major_change": (
            "You are an expert technical writer. Based on the provided context (code diff, commit logs, PR discussions, and API diff), "
            "generate release notes for this new MAJOR version. Focus on: 1) API-breaking changes, 2) migrations, 3) deprecated removals."
        ),
        "minor_change": (
            "You are an expert technical writer. Based on the provided context (code diff, commit logs, PR discussions, and API diff), "
            "generate release notes for this MINOR version. Focus on: 1) new API features, 2) deprecations, 3) important fixes."
        ),
        "bugfix": (
            "You are an expert technical writer. Based on the provided context (code diff, commit logs, PR discussions, and API diff), "
            "generate release notes for this PATCH version. Focus on bug fixes and stability improvements."
        ),
    },
    "application": {
        "major_change": (
            "You are an expert technical writer. Summarize significant user-facing feature changes or removals. Highlight breaking changes and migration steps."
        ),
        "minor_change": (
            "You are an expert technical writer. Summarize new user-facing features and enhancements."
        ),
        "bugfix": (
            "You are an expert technical writer. Summarize bug fixes and behavioral corrections."
        ),
    },
}


@dataclass
class ReleaseNotesConfig:
    project_type: str = "library"
    public_api_command: Optional[str] = None
    prompts: Dict[str, Dict[str, str]] = None
    model_name: str = "gemini-2.5-flash"

    @staticmethod
    def load(config_path: Optional[str], repo_root: Optional[str]) -> "ReleaseNotesConfig":
        path = config_path
        if path is None and repo_root is not None:
            candidate = os.path.join(repo_root, ".releasenotes.yml")
            if os.path.isfile(candidate):
                path = candidate
        if path is None or not os.path.isfile(path):
            return ReleaseNotesConfig(project_type="library", public_api_command=None, prompts=DEFAULT_PROMPTS, model_name="gemini-2.5-flash")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        project_type = data.get("project_type", "library")
        public_api_command = data.get("public_api_command")
        model_name = data.get("gemini_model", "gemini-2.5-flash")
        prompts = DEFAULT_PROMPTS.copy()
        user_prompts = data.get("prompts") or {}
        for domain, entries in user_prompts.items():
            if domain not in prompts:
                prompts[domain] = {}
            for k, v in (entries or {}).items():
                prompts[domain][k] = v
        return ReleaseNotesConfig(project_type=project_type, public_api_command=public_api_command, prompts=prompts, model_name=model_name)


SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def parse_semver_tag(tag: str) -> Optional[tuple[int, int, int]]:
    m = SEMVER_RE.match(tag)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


