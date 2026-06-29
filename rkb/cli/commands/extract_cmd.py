"""Extract command - Extract content from PDF documents."""
# ruff: noqa: T201

import argparse
from pathlib import Path


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add command-specific arguments."""
    parser.add_argument("files", nargs="+", type=Path, help="PDF files to extract")

    parser.add_argument(
        "--extractor",
        choices=["nougat"],
        default="nougat",
        help="Extractor to use (default: nougat)",
    )

    parser.add_argument(
        "--max-pages", type=int, default=500, help="Maximum pages per PDF (default: 500)"
    )

    parser.add_argument("--project-id", help="Project ID to associate documents with")

    parser.add_argument(
        "--force-reprocess", action="store_true", help="Force reprocessing of existing documents"
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        default=True,
        help="Resume from checkpoint if available (default: True)",
    )

    parser.add_argument("--no-resume", action="store_true", help="Do not resume from checkpoint")

    parser.add_argument(
        "--checkpoint-dir", type=Path, help="Directory for checkpoint files (default: .checkpoints)"
    )

    parser.add_argument(
        "--db-path",
        type=Path,
        default="rkb_documents.db",
        help="Path to document registry database (default: rkb_documents.db)",
    )

    parser.add_argument(
        "--extraction-dir",
        type=Path,
        default=Path("rkb_extractions"),
        help="Directory for extraction output (default: rkb_extractions)",
    )


def execute(_args: argparse.Namespace) -> int:
    """Execute the extract command."""
    print("This command is deprecated. Use 'rkb translate' + 'rkb index' instead.")
    return 1
