"""Find command - Find recent PDF files."""
# ruff: noqa: T201

import argparse
from pathlib import Path

from rkb.core.document_registry import DocumentRegistry
from rkb.services.project_service import ProjectService


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


def execute(args: argparse.Namespace) -> int:
    """Execute the find command."""
    try:
        # Initialize services
        registry = DocumentRegistry(args.db_path)
        project_service = ProjectService(registry)

        # Find recent PDFs
        files = project_service.find_recent_pdfs(
            data_dir=args.data_dir,
            num_files=args.num_files,
            output_file=args.output_file,
            project_id=args.project_id
        )

        # Display results
        print(f"\n📄 Found {len(files)} recent PDF files:")
        for i, file_info in enumerate(files[:20], 1):
            print(
                f"  {i:2d}. {file_info['name']} ({file_info['size_mb']:.1f} MB) - "
                f"{file_info['modified_date']}"
            )

        if len(files) > 20:
            print(f"  ... and {len(files) - 20} more files")

        if args.output_file:
            print(f"\n💾 File list saved to: {args.output_file}")

        return 0

    except Exception as e:
        print(f"✗ Find command failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1
