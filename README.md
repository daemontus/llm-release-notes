## Automated Release Note Generator

Python tool that generates comprehensive release notes by building a rich diff context between two Git refs and synthesizing human-readable notes with an LLM.

### Features
- Diff Context Generator: code diff, commit logs, PR discussions, optional public API diff.
- Release Note Synthesizer: SemVer-aware comparisons, config-driven prompts, Gemini integration.

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
python -m llm_release_notes.cli diff-context \
  --repo git@github.com:owner/repo.git \
  --base v1.0.0 \
  --head v1.1.0 \
  --output-dir /tmp/context
```

2) Release Note Synthesizer
```bash
python -m llm_release_notes.cli synthesize \
  --repo git@github.com:owner/repo.git \
  --version v1.2.0 \
  --config optional/path/to/.releasenotes.yml \
  --output notes.md
```

### Config
The tool looks for `.releasenotes.yml` in the repository root or accepts a path via `--config`.

```yaml
project_type: library
public_api_command: "cargo public-api"
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

### Example repo
You can test with `git@github.com:sybila/biodivine-lib-bdd.git`.


