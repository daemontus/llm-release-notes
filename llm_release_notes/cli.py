"""Command-line interface for the Release Notes tool."""

import argparse
import logging
import os
import sys
import tempfile

from .config import ReleaseNotesConfig
from .diff_context import generate_diff_context, write_file
from .exceptions import LLMAPIError, llmReleaseNotesError
from .git_utils import checkout_ref, clone_or_fetch, list_tags, verify_ref_exists
from .synthesizer import comparison_title, select_comparisons_single_version, synthesize_notes_for_range


def cmd_diff_context(args: argparse.Namespace) -> None:
    # Ensure repo is available so .releasenotes.yml in repo root can be resolved
    repo_dir = clone_or_fetch(args.repo)
    # The fresh working copy has nothing checked out; use the config from the head ref.
    checkout_ref(repo_dir, args.head)
    cfg = ReleaseNotesConfig.load(args.config, repo_dir)
    logging.getLogger(__name__).info(
        "Generating diff context: repo=%s base=%s head=%s output=%s",
        args.repo,
        args.base or "(empty repository)",
        args.head,
        args.output_dir,
    )
    logging.getLogger(__name__).info(
        "Settings: public_api_command=%s, config=%s",
        "yes" if bool(cfg.public_api_command) else "no",
        args.config or "repo/.releasenotes.yml or defaults",
    )
    generate_diff_context(
        repo_url=args.repo,
        base=args.base,
        head=args.head,
        output_dir=args.output_dir,
        public_api_command=cfg.public_api_command,
        diff_exclude_paths=cfg.diff_exclude_paths,
    )


def cmd_synthesize(args: argparse.Namespace) -> None:
    repo_dir = clone_or_fetch(args.repo)
    tags = list_tags(repo_dir)
    if not verify_ref_exists(repo_dir, args.version):
        raise llmReleaseNotesError(f"Version {args.version} does not exist in repository")
    # The fresh working copy has nothing checked out; use the config from the released version.
    checkout_ref(repo_dir, args.version)
    cfg = ReleaseNotesConfig.load(args.config, repo_dir)
    if args.model:
        cfg.model = args.model
    if args.base_url:
        cfg.base_url = args.base_url
    if args.max_context_tokens:
        cfg.max_context_tokens = args.max_context_tokens
    cfg.validate_for_synthesis()
    # Fail fast, before the (possibly long) context generation.
    if not os.environ.get(cfg.api_key_env):
        raise LLMAPIError(f"Environment variable {cfg.api_key_env} with the LLM API key is not set")
    output_path = args.output
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # We intentionally do not put the version number here, because it is already displayed by GitHub GUI
    preamble = "*(this summary is LLM-generated, but validated by project developers)*\n\n"

    if args.previous_version:
        if not (verify_ref_exists(repo_dir, args.previous_version) and verify_ref_exists(repo_dir, args.version)):
            raise llmReleaseNotesError(f"Version {args.previous_version} does not exist in repository")
        with tempfile.TemporaryDirectory(prefix="rn_ctx_") as tmp:
            logging.getLogger(__name__).info("Synthesizing notes for explicit range %s..%s", args.previous_version, args.version)
            notes = synthesize_notes_for_range(args.repo, args.previous_version, args.version, cfg, tmp)
        write_file(output_path, preamble + notes)
        return

    # Single-version mode
    comparisons = select_comparisons_single_version(args.version, tags)
    logging.getLogger(__name__).info("Selected %d comparison(s) for version %s", len(comparisons), args.version)
    logging.getLogger(__name__).info(
        "Settings: project_type=%s, model=%s, config=%s", cfg.project_type, cfg.model, args.config or "default"
    )
    sections = []
    for base, head in comparisons:
        title = comparison_title(base, head)
        with tempfile.TemporaryDirectory(prefix="rn_ctx_") as tmp:
            logging.getLogger(__name__).info("Synthesizing notes: %s", title)
            section_body = synthesize_notes_for_range(args.repo, base, head, cfg, tmp)
        sections.append(f"## {title}\n\n{section_body}\n")
    write_file(output_path, preamble + "\n".join(sections))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="llm-release-notes", description="Automated Release Note Generator")
    sub = p.add_subparsers(dest="command", required=True)
    p.add_argument("--verbose", action="store_true", help="Enable verbose logging to console")

    p_diff = sub.add_parser("diff-context", help="Generate diff context between two refs")
    p_diff.add_argument("--repo", required=True)
    p_diff.add_argument("--base", help="Base ref; omit to compare against an empty repository (first release)")
    p_diff.add_argument("--head", required=True)
    p_diff.add_argument("--output-dir", required=True)
    p_diff.add_argument("--config", required=False)
    p_diff.set_defaults(func=cmd_diff_context)

    p_syn = sub.add_parser("synthesize", help="Synthesize release notes")
    p_syn.add_argument("--repo", required=True)
    p_syn.add_argument("--version", required=True)
    p_syn.add_argument("--previous-version")
    p_syn.add_argument("--config")
    p_syn.add_argument("--output", required=True)
    p_syn.add_argument("--model", help="Model name (overrides config 'model')")
    p_syn.add_argument("--base-url", help="Base URL of the OpenAI-compatible endpoint (overrides config 'base_url')")
    p_syn.add_argument(
        "--max-context-tokens", type=int, help="Context window of the model in tokens (overrides config 'max_context_tokens')"
    )
    p_syn.set_defaults(func=cmd_synthesize)
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING, format="[%(levelname)s] %(message)s"
    )
    try:
        args.func(args)
    except llmReleaseNotesError as e:
        logging.getLogger(__name__).error(e)
        sys.exit(1)


if __name__ == "__main__":
    main()


