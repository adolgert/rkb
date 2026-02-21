"""Main CLI entry point for the RKB (Research Knowledge Base) system."""
# ruff: noqa: T201

import argparse
import logging
import sys
from pathlib import Path

from rkb.cli.commands import (
    documents_cmd,
    enrich_cmd,
    index_cmd,
    ingest_cmd,
    rectify_cmd,
    remove_cmd,
    search_cmd,
    status_cmd,
    translate_cmd,
    triage_cmd,
)


def create_parser() -> argparse.ArgumentParser:
    """Create the main argument parser with subcommands."""
    # Shared options available on every subcommand (and on the top-level parser)
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    shared.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file"
    )

    parser = argparse.ArgumentParser(
        prog="rkb",
        description="Research Knowledge Base - PDF processing and semantic search system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[shared],
        epilog="""
Examples:
  rkb ingest ~/papers
  rkb translate
  rkb index --embedder specter2
  rkb search "machine learning transformers"
        """,
    )

    # Create subparsers for commands
    subparsers = parser.add_subparsers(
        dest="command",
        help="Available commands",
        metavar="COMMAND"
    )

    # Search command (chunk-level)
    search_parser = subparsers.add_parser(
        "search",
        parents=[shared],
        help="Search for chunks in the corpus",
        description="Perform semantic search over indexed chunks"
    )
    search_cmd.add_arguments(search_parser)

    # Documents command (document-level)
    documents_parser = subparsers.add_parser(
        "documents",
        parents=[shared],
        help="Search for documents using ranking",
        description="Perform document-level semantic search with ranking metrics"
    )
    documents_cmd.add_arguments(documents_parser)

    # Index command
    index_parser = subparsers.add_parser(
        "index",
        parents=[shared],
        help="Index documents for search",
        description="Create embeddings and index documents for semantic search"
    )
    index_cmd.add_arguments(index_parser)

    # Ingest command
    ingest_parser = subparsers.add_parser(
        "ingest",
        parents=[shared],
        help="Ingest PDFs into canonical content-addressed storage",
        description="Scan one or more directories and ingest discovered PDFs",
    )
    ingest_cmd.add_arguments(ingest_parser)

    # Enrich command
    enrich_parser = subparsers.add_parser(
        "enrich",
        parents=[shared],
        help="Resolve metadata and rename PDFs in canonical collection",
        description="Run metadata extractors on unresolved papers and rename files",
    )
    enrich_cmd.add_arguments(enrich_parser)

    # Rectify command
    rectify_parser = subparsers.add_parser(
        "rectify",
        parents=[shared],
        help="Reconcile scattered PDFs into canonical store and Zotero",
        description="Run one-time bidirectional reconciliation of PDF collections",
    )
    rectify_cmd.add_arguments(rectify_parser)

    # Translate command
    translate_parser = subparsers.add_parser(
        "translate",
        parents=[shared],
        help="Translate PDFs to Markdown using marker-pdf",
        description="Convert PDFs in the canonical store to Markdown using marker-pdf with Gemini",
    )
    translate_cmd.add_arguments(translate_parser)

    # Triage command
    triage_parser = subparsers.add_parser(
        "triage",
        parents=[shared],
        help="Launch local work-side PDF triage app",
        description="Review PDFs from downloads and stage approved files",
    )
    triage_cmd.add_arguments(triage_parser)

    # Status command
    status_parser = subparsers.add_parser(
        "status",
        parents=[shared],
        help="Show canonical collection and Zotero sync status",
        description="Report canonical counts, Zotero coverage, and recent ingest activity",
    )
    status_cmd.add_arguments(status_parser)

    # Remove command
    remove_parser = subparsers.add_parser(
        "remove",
        parents=[shared],
        help="Remove a PDF and all associated data from the collection",
        description="Delete a PDF by title fragment or sha256 hash, cleaning up all records",
    )
    remove_cmd.add_arguments(remove_parser)

    return parser


def main(args: list[str] | None = None) -> int:  # noqa: PLR0912
    """Main CLI entry point."""
    parser = create_parser()
    parsed_args = parser.parse_args(args)

    # If no command specified, show help
    if not parsed_args.command:
        parser.print_help()
        return 1

    # Set up logging configuration
    log_level = logging.DEBUG if parsed_args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Route to appropriate command handler
    try:
        if parsed_args.command == "search":
            return search_cmd.execute(parsed_args)
        if parsed_args.command == "documents":
            return documents_cmd.execute(parsed_args)
        if parsed_args.command == "index":
            return index_cmd.execute(parsed_args)
        if parsed_args.command == "ingest":
            return ingest_cmd.execute(parsed_args)
        if parsed_args.command == "enrich":
            return enrich_cmd.execute(parsed_args)
        if parsed_args.command == "rectify":
            return rectify_cmd.execute(parsed_args)
        if parsed_args.command == "translate":
            return translate_cmd.execute(parsed_args)
        if parsed_args.command == "triage":
            return triage_cmd.execute(parsed_args)
        if parsed_args.command == "status":
            return status_cmd.execute(parsed_args)
        if parsed_args.command == "remove":
            return remove_cmd.execute(parsed_args)
        print(f"Unknown command: {parsed_args.command}")
        return 1

    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        return 130
    except Exception as e:
        if parsed_args.verbose:
            import traceback
            traceback.print_exc()
        else:
            print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
