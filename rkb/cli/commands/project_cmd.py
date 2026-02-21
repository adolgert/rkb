"""Project command - Manage document projects."""
# ruff: noqa: T201

import argparse
from pathlib import Path


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add command-specific arguments."""
    subparsers = parser.add_subparsers(
        dest="action",
        help="Project actions",
        metavar="ACTION"
    )

    # Create project
    create_parser = subparsers.add_parser("create", help="Create a new project")
    create_parser.add_argument("name", help="Project name")
    create_parser.add_argument("--description", help="Project description")
    create_parser.add_argument("--data-dir", type=Path, help="Project data directory")

    # List projects
    subparsers.add_parser("list", help="List all projects")

    # Show project details
    show_parser = subparsers.add_parser("show", help="Show project details")
    show_parser.add_argument("project_id", help="Project ID")

    # Find recent PDFs
    find_parser = subparsers.add_parser("find-pdfs", help="Find recent PDFs")
    find_parser.add_argument("--data-dir", type=Path, required=True, help="Directory to search")
    find_parser.add_argument(
        "--num-files", type=int, default=50, help="Number of files (default: 50)"
    )
    find_parser.add_argument("--output-file", type=Path, help="Save file list to JSON")
    find_parser.add_argument("--project-id", help="Associate with project")

    # Create document subset
    subset_parser = subparsers.add_parser("subset", help="Create document subset")
    subset_parser.add_argument("name", help="Subset name")
    subset_parser.add_argument("--project-id", help="Project to filter by")
    subset_parser.add_argument(
        "--status",
        choices=["pending", "extracting", "extracted", "indexing", "indexed", "failed"],
        help="Filter by status"
    )
    subset_parser.add_argument("--date-from", help="Filter by date (YYYY-MM-DD)")
    subset_parser.add_argument("--date-to", help="Filter by date (YYYY-MM-DD)")
    subset_parser.add_argument("--filename-pattern", help="Filter by filename pattern")
    subset_parser.add_argument("--limit", type=int, help="Limit number of results")

    # Export project data
    export_parser = subparsers.add_parser("export", help="Export project data")
    export_parser.add_argument("project_id", help="Project ID")
    export_parser.add_argument("--output-file", type=Path, required=True, help="Output JSON file")
    export_parser.add_argument(
        "--include-content", action="store_true", help="Include extracted content"
    )

    # Global options
    parser.add_argument(
        "--db-path",
        type=Path,
        default="rkb_documents.db",
        help="Path to document registry database (default: rkb_documents.db)"
    )


def execute(_args: argparse.Namespace) -> int:
    """Execute the project command."""
    print("This command is deprecated. Use 'rkb translate' + 'rkb index' instead.")
    return 1
