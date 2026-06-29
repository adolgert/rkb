"""Experiment command - Manage experiments and comparisons."""
# ruff: noqa: T201

import argparse
from pathlib import Path


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add command-specific arguments."""
    subparsers = parser.add_subparsers(
        dest="action",
        help="Experiment actions",
        metavar="ACTION"
    )

    # Create experiment
    create_parser = subparsers.add_parser("create", help="Create a new experiment")
    create_parser.add_argument("name", help="Experiment name")
    create_parser.add_argument("--extractor", default="nougat", help="Extractor to use")
    create_parser.add_argument("--embedder", default="chroma", help="Embedder to use")
    create_parser.add_argument("--chunk-size", type=int, default=2000, help="Text chunk size")
    create_parser.add_argument("--search-strategy", default="semantic_only", help="Search strategy")
    create_parser.add_argument("--vector-db-path", type=Path, help="Vector database path")
    create_parser.add_argument("--project-id", help="Associated project ID")
    create_parser.add_argument("--description", help="Experiment description")

    # List experiments
    list_parser = subparsers.add_parser("list", help="List experiments")
    list_parser.add_argument("--project-id", help="Filter by project")

    # Run experiment
    run_parser = subparsers.add_parser("run", help="Run search experiment")
    run_parser.add_argument("experiment_id", help="Experiment ID")
    run_parser.add_argument("queries", nargs="+", help="Search queries")
    run_parser.add_argument("--num-results", type=int, default=5, help="Results per query")

    # Compare experiments
    compare_parser = subparsers.add_parser("compare", help="Compare experiments")
    compare_parser.add_argument("experiment_ids", nargs="+", help="Experiment IDs to compare")
    compare_parser.add_argument("--queries", nargs="+", required=True, help="Test queries")
    compare_parser.add_argument("--num-results", type=int, default=5, help="Results per query")

    # Show summary
    subparsers.add_parser("summary", help="Show experiment summary")

    # Global options
    parser.add_argument(
        "--db-path",
        type=Path,
        default="rkb_documents.db",
        help="Path to document registry database (default: rkb_documents.db)"
    )


def execute(_args: argparse.Namespace) -> int:
    """Execute the experiment command."""
    print("This command is deprecated. Use 'rkb translate' + 'rkb index' instead.")
    return 1
