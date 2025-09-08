import argparse
import logging
import os
import tempfile

from .config import ReleaseNotesConfig
from .diff_context import generate_diff_context, write_file
from .git_utils import clone_or_fetch, list_tags, verify_ref_exists
from .synthesizer import select_comparisons_single_version, synthesize_notes_for_range


def cmd_diff_context(args: argparse.Namespace) -> None:
    cfg = ReleaseNotesConfig.load(args.config, None)
    logging.getLogger(__name__).info(
        "Generating diff context: repo=%s base=%s head=%s output=%s",
        args.repo,
        args.base,
        args.head,
        args.output_dir,
    )
    generate_diff_context(
        repo_url=args.repo,
        base=args.base,
        head=args.head,
        output_dir=args.output_dir,
        public_api_command=cfg.public_api_command,
    )


def cmd_synthesize(args: argparse.Namespace) -> None:
    repo_dir = clone_or_fetch(args.repo)
    tags = list_tags(repo_dir)
    cfg = ReleaseNotesConfig.load(args.config, repo_dir)
    if getattr(args, "gemini_model", None):
        cfg.model_name = args.gemini_model
    output_path = args.output
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    if args.previous_version:
        if not (verify_ref_exists(repo_dir, args.previous_version) and verify_ref_exists(repo_dir, args.version)):
            raise SystemExit("Provided tags do not exist in repository")
        with tempfile.TemporaryDirectory(prefix="rn_ctx_") as tmp:
            logging.getLogger(__name__).info("Synthesizing notes for explicit range %s..%s", args.previous_version, args.version)
            notes = synthesize_notes_for_range(args.repo, args.previous_version, args.version, cfg, tmp)
        write_file(output_path, notes)
        return

    # Single-version mode
    comparisons = select_comparisons_single_version(args.version, tags)
    logging.getLogger(__name__).info("Selected %d comparison(s) for version %s", len(comparisons), args.version)
    sections = []
    for base, head in comparisons:
        if not base:
            continue
        with tempfile.TemporaryDirectory(prefix="rn_ctx_") as tmp:
            logging.getLogger(__name__).info("Synthesizing notes for range %s..%s", base, head)
            section_body = synthesize_notes_for_range(args.repo, base, head, cfg, tmp)
        title = f"## Changes Since {base}"
        sections.append(f"{title}\n\n{section_body}\n")
    write_file(output_path, "\n".join(sections))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="llm-release-notes", description="Automated Release Note Generator")
    sub = p.add_subparsers(dest="command", required=True)
    p.add_argument("--verbose", action="store_true", help="Enable verbose logging to console")

    p_diff = sub.add_parser("diff-context", help="Generate diff context between two refs")
    p_diff.add_argument("--repo", required=True)
    p_diff.add_argument("--base", required=True)
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
    p_syn.add_argument("--gemini-model", dest="gemini_model", help="Override Gemini model name (config gemini_model)")
    p_syn.set_defaults(func=cmd_synthesize)
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="[%(levelname)s] %(message)s")
    args.func(args)


if __name__ == "__main__":
    main()


