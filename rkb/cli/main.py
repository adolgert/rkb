#!/usr/bin/env python3
"""Main CLI entry point for the RKB (Research Knowledge Base) system."""
# ruff: noqa: T201

import argparse
import logging
import sys
from pathlib import Path

from rkb.cli.commands import (
    experiment_cmd,
    extract_cmd,
    find_cmd,
    index_cmd,
    pipeline_cmd,
    project_cmd,
    search_cmd,
)


def create_parser() -> argparse.ArgumentParser:
    """Create the main argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="rkb",
        description="Research Knowledge Base - PDF processing and semantic search system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  rkb pipeline --data-dir data/papers --num-files 20
  rkb search "machine learning transformers"
  rkb find --data-dir data/papers --num-files 50
  rkb index --extractor nougat --embedder ollama
  rkb project create "My Research Project"
  rkb experiment create "Test Setup" --embedder chroma
        """,
    )

    # Global options
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )

    parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file"
    )

    # Create subparsers for commands
    subparsers = parser.add_subparsers(
        dest="command",
        help="Available commands",
        metavar="COMMAND"
    )

    # Pipeline command
    pipeline_parser = subparsers.add_parser(
        "pipeline",
        help="Run complete PDF processing pipeline",
        description="Process PDFs from finding recent files through indexing for search"
    )
    pipeline_cmd.add_arguments(pipeline_parser)

    # Search command
    search_parser = subparsers.add_parser(
        "search",
        help="Search the document corpus",
        description="Perform semantic search over indexed documents"
    )
    search_cmd.add_arguments(search_parser)

    # Index command
    index_parser = subparsers.add_parser(
        "index",
        help="Index documents for search",
        description="Create embeddings and index documents for semantic search"
    )
    index_cmd.add_arguments(index_parser)

    # Find command
    find_parser = subparsers.add_parser(
        "find",
        help="Find recent PDF files",
        description="Discover recent PDF files in a directory"
    )
    find_cmd.add_arguments(find_parser)

    # Extract command
    extract_parser = subparsers.add_parser(
        "extract",
        help="Extract content from PDFs",
        description="Extract text and structure from PDF documents"
    )
    extract_cmd.add_arguments(extract_parser)

    # Project command
    project_parser = subparsers.add_parser(
        "project",
        help="Manage document projects",
        description="Create and manage document collections"
    )
    project_cmd.add_arguments(project_parser)

    # Experiment command
    experiment_parser = subparsers.add_parser(
        "experiment",
        help="Manage experiments",
        description="Create and compare different processing configurations"
    )
    experiment_cmd.add_arguments(experiment_parser)

    return parser


def main(args: list[str] | None = None) -> int:
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
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Route to appropriate command handler
    try:
        if parsed_args.command == "pipeline":
            return pipeline_cmd.execute(parsed_args)
        if parsed_args.command == "search":
            return search_cmd.execute(parsed_args)
        if parsed_args.command == "index":
            return index_cmd.execute(parsed_args)
        if parsed_args.command == "find":
            return find_cmd.execute(parsed_args)
        if parsed_args.command == "extract":
            return extract_cmd.execute(parsed_args)
        if parsed_args.command == "project":
            return project_cmd.execute(parsed_args)
        if parsed_args.command == "experiment":
            return experiment_cmd.execute(parsed_args)
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
