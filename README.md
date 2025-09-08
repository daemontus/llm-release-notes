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

### GitHub Actions example (generate notes and create a draft release)
Below is a minimal workflow that: installs dependencies, runs the synthesizer on tag push, and creates a draft release with the generated notes.

Save as `.github/workflows/release-notes.yml` in your repository:

```yaml
name: Generate Release Notes

on:
  push:
    tags:
      - 'v*.*.*'

jobs:
  generate-notes:
    runs-on: ubuntu-latest
    permissions:
      contents: write  # required to create a release

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install llm-release-notes
        run: |
          python -m venv .venv
          source .venv/bin/activate
          pip install git+https://github.com/daemontus/llm-release-notes.git

      - name: Determine version
        id: version
        run: |
          TAG_REF="${GITHUB_REF#refs/tags/}"
          echo "tag=${TAG_REF}" >> $GITHUB_OUTPUT

      - name: Generate release notes
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: |
          source .venv/bin/activate
          python -m llm_release_notes.cli --verbose synthesize \
            --repo ${{ github.repositoryUrl }} \
            --version ${{ steps.version.outputs.tag }} \
            --output release-notes.md \
            --config .releasenotes.yml

      - name: Create draft release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ steps.version.outputs.tag }}
          draft: true
          body_path: release-notes.md
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Notes:
- Ensure `.releasenotes.yml` exists at repo root, ideally with `public_api_command` configured (especially for libraries).
- Set `GEMINI_API_KEY` in your repository secrets.
- By default GitHub provides `GITHUB_TOKEN` to workflows; it’s used to fetch PR discussions and create the release.

