"""Find command - Find recent PDF files."""
# ruff: noqa: T201

import argparse
from pathlib import Path


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add command-specific arguments."""
    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Directory to search for PDFs"
    )

    parser.add_argument(
        "--num-files",
        type=int,
        default=50,
        help="Number of recent files to find (default: 50)"
    )

    parser.add_argument(
        "--output-file",
        type=Path,
        help="Save file list to JSON file"
    )

    parser.add_argument(
        "--project-id",
        help="Associate files with project"
    )

    parser.add_argument(
        "--db-path",
        type=Path,
        default="rkb_documents.db",
        help="Path to document registry database (default: rkb_documents.db)"
    )


def execute(_args: argparse.Namespace) -> int:
    """Execute the find command."""
    print("This command is deprecated. Use 'rkb translate' + 'rkb index' instead.")
    return 1
