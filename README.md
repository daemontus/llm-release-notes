## Automated Release Note Generator

Python tool that generates comprehensive release notes by building a rich diff context between two Git refs and synthesizing human-readable notes with an LLM. Any OpenAI-compatible chat completions endpoint can be used (OpenAI, OpenRouter, vLLM, Ollama, ...).

### Features
- Diff Context Generator: code diff, commit logs, PR discussions, optional public API diff.
- Release Note Synthesizer: SemVer-aware comparisons with non-overlapping ranges, config-driven prompts, works with any OpenAI-compatible API.
- First releases are supported: if there is no earlier version, the release is compared against an empty repository.
- Context that does not fit into the model is shortened in a controlled way (see [Context window](#context-window)).

### Requirements
- Python 3.9+
- git installed and in PATH
- Environment variables:
  - `LLM_API_KEY` with the API key of the LLM endpoint (the variable name can be changed with `api_key_env`)
  - `GITHUB_TOKEN` for GitHub API (required for PR discussions)

### Install
```bash
python -m venv .venv && source .venv/bin/activate
pip install .
```

### Usage
Two main commands:

1) Diff Context Generator (no LLM involved; useful to inspect what the model will see)
```bash
python -m llm_release_notes.cli --verbose diff-context \
  --repo git@github.com:owner/repo.git \
  --base v1.0.0 \
  --head v1.1.0 \
  --output-dir /tmp/context \
  --config path/to/.releasenotes.yml
```
Omit `--base` to compare `--head` against an empty repository.

2) Release Note Synthesizer
```bash
export GITHUB_TOKEN=... LLM_API_KEY=...
python -m llm_release_notes.cli --verbose synthesize \
  --repo git@github.com:owner/repo.git \
  --version v2.0.0 \
  --output notes.md \
  --config path/to/.releasenotes.yml
```

The model settings can also be given (or overridden) on the command line:
```bash
python -m llm_release_notes.cli --verbose synthesize \
  --repo git@github.com:owner/repo.git \
  --version v1.2.0 \
  --output notes.md \
  --base-url https://openrouter.ai/api/v1 \
  --model google/gemini-3.5-flash \
  --max-context-tokens 1048576
```

Without `--previous-version`, the tool picks the versions to compare against automatically and writes one section per comparison, titled e.g. `## Changes for v1.1.0..v1.1.5`:
- bugfix release `v1.2.3`: `v1.2.2..v1.2.3`
- minor release `v1.2.0`: `v1.1.5..v1.2.0` and `v1.1.0..v1.1.5`
- major release `v2.0.0`: `v1.5.2..v2.0.0`, `v1.5.0..v1.5.2` and `v1.0.0..v1.5.0`
- first release (no earlier SemVer tag): the whole project, titled `## Changes for v1.0.0 (initial release)`

### Config
The tool looks for `.releasenotes.yml` in the repository root (at the version being released) or accepts a path via `--config`.

```yaml
project_type: library

# Prints the public API of the project; it is run on both versions and the outputs are diffed.
# For Rust, omitting blanket implementations removes a lot of auto-generated noise, so the diff
# mostly contains things that were actually changed (`-s` / `-ss` / `-sss` omit even more).
public_api_command: "cargo public-api --omit blanket-impls"

# LLM endpoint (any OpenAI-compatible chat completions API). Required: model, max_context_tokens.
base_url: https://openrouter.ai/api/v1   # omit for api.openai.com
model: google/gemini-3.5-flash
max_context_tokens: 1048576              # context window of the model, see your provider's model page
# reserved_output_tokens: 8192           # part of the context window kept free for the output
# api_key_env: LLM_API_KEY               # environment variable with the API key

# Project-wide instructions appended to every prompt
project_prompt: |
  Prefer Rust examples and reference key public types.

# Exclude irrelevant paths from the diff (git pathspecs, passed as :!path)
diff_exclude_paths:
  - tests/data/**
  - docs/generated/**
  - Cargo.lock

# Customize base prompts that are used for every change comparison
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
    initial_release: |
      Summarize the main features...
  application:
    major_change: |
      Summarize major user-facing changes...
```

Other endpoints only need a different `base_url` / `model` / `max_context_tokens`, e.g.:

| Provider | `base_url` | Notes |
|---|---|---|
| OpenAI | *(omit)* | |
| OpenRouter | `https://openrouter.ai/api/v1` | model ids like `google/gemini-3.5-flash` |
| vLLM | `http://localhost:8000/v1` | `max_context_tokens` = the server's `--max-model-len` |
| Ollama | `http://localhost:11434/v1` | `max_context_tokens` = the model's configured `num_ctx` (see below) |

For local servers that do not check the API key, set `LLM_API_KEY` to any non-empty value.

### Context window
OpenAI-compatible APIs have no portable way to count tokens before sending a request, so the tool estimates them conservatively (~3 characters per token) and fits the context into `max_context_tokens - reserved_output_tokens`:
1. If everything fits, it is sent unchanged.
2. Otherwise, the code diff is first regenerated without context lines.
3. Commit logs, PR discussions and the public API diff together get at most half of the budget; if they are larger, they are truncated evenly.
4. The code diff gets the rest. Files are kept in order; a file whose diff does not fit is omitted as a whole (smaller files after it may still fit), and the omitted files are listed so that the model knows they changed.

Every shortening is logged as a warning and also mentioned to the model. Use `diff_exclude_paths` to drop irrelevant large files (lockfiles, generated code, test data) up front.

**Ollama silently truncates** input that exceeds its configured context size instead of returning an error. Make sure `max_context_tokens` matches the `num_ctx` the model actually runs with. The tool warns if the server reports far fewer input tokens than expected, which usually indicates such truncation.

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
        uses: actions/checkout@v5

      - name: Set up Python
        uses: actions/setup-python@v6
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
          LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
        run: |
          source .venv/bin/activate
          python -m llm_release_notes.cli --verbose synthesize \
            --repo https://github.com/${{ github.repository }}.git \
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
- The tool clones the repository itself using the `--repo` URL. This works as-is for public repositories. For private repositories, use a URL the runner can authenticate with, e.g. `https://x-access-token:${{ secrets.GITHUB_TOKEN }}@github.com/${{ github.repository }}.git`.
- Set `LLM_API_KEY` in your repository secrets, and configure `model`, `max_context_tokens` (and `base_url`, unless you use OpenAI) in `.releasenotes.yml`.
- By default GitHub provides `GITHUB_TOKEN` to workflows; it’s used to fetch PR discussions and create the release.

