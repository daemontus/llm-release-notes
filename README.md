## Automated Release Note Generator

Python tool that generates comprehensive release notes by building a rich diff context between two Git refs and synthesizing human-readable notes with an LLM (Google Gemini).

### Features
- Diff Context Generator: code diff, commit logs, PR discussions, optional public API diff.
- Release Note Synthesizer: SemVer-aware comparisons with non-overlapping ranges, config-driven prompts, Gemini integration.

### Requirements
- Python 3.8+
- git installed and in PATH
- Environment variables:
  - `GITHUB_TOKEN` for GitHub API (required for PR discussions)
  - `GEMINI_API_KEY` for Google Gemini

### Install
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Usage
Two main commands:

1) Diff Context Generator
```bash
python -m llm_release_notes.cli --verbose diff-context \
  --repo git@github.com:owner/repo.git \
  --base v1.0.0 \
  --head v1.1.0 \
  --output-dir /tmp/context \
  --config path/to/.releasenotes.yml
```

2) Release Note Synthesizer
```bash
export GITHUB_TOKEN=... GEMINI_API_KEY=...
python -m llm_release_notes.cli --verbose synthesize \
  --repo git@github.com:owner/repo.git \
  --version v2.0.0 \
  --output notes.md \
  --config path/to/.releasenotes.yml
```

Override Gemini model (default: gemini-2.5-flash):
```bash
python -m llm_release_notes.cli --verbose synthesize \
  --repo git@github.com:owner/repo.git \
  --version v1.2.0 \
  --output notes.md \
  --gemini-model gemini-2.0-pro
```

### Config
The tool looks for `.releasenotes.yml` in the repository root or accepts a path via `--config`.

```yaml
project_type: library
public_api_command: "cargo public-api --diff-no-blanket-impls"

# Gemini model selection (default is gemini-2.5-flash)
gemini_model: gemini-2.5-flash

# Project-wide instructions appended to every prompt
project_prompt: |
  Prefer Rust examples and reference key public types.

# Exclude irrelevant paths from the diff (git pathspecs, passed as :!path)
diff_exclude_paths:
  - tests/data/**
  - docs/generated/**
# Customize base prompts that are used for every change comaprison 
# (together with the project prompt). These are a bit more advanced,
# so it is recommended to first look at `config.py` at some examples
# of how these could look.
prompts:
  library:
    major_change: |
      Summarize breaking API changes...
    minor_change: |
      Summarize new API features...
    bugfix: |
      Summarize bug fixes...
  application:
    major_change: |
      Summarize major user-facing changes...
```

