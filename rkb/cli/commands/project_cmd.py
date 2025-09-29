"""Project command - Manage document projects."""
# ruff: noqa: T201

import argparse
from pathlib import Path

from rkb.core.document_registry import DocumentRegistry
from rkb.services.project_service import ProjectService


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
    find_parser.add_argument("--num-files", type=int, default=50, help="Number of files (default: 50)")
    find_parser.add_argument("--output-file", type=Path, help="Save file list to JSON")
    find_parser.add_argument("--project-id", help="Associate with project")

    # Create document subset
    subset_parser = subparsers.add_parser("subset", help="Create document subset")
    subset_parser.add_argument("name", help="Subset name")
    subset_parser.add_argument("--project-id", help="Project to filter by")
    subset_parser.add_argument("--status", choices=["pending", "extracting", "extracted", "indexing", "indexed", "failed"], help="Filter by status")
    subset_parser.add_argument("--date-from", help="Filter by date (YYYY-MM-DD)")
    subset_parser.add_argument("--date-to", help="Filter by date (YYYY-MM-DD)")
    subset_parser.add_argument("--filename-pattern", help="Filter by filename pattern")
    subset_parser.add_argument("--limit", type=int, help="Limit number of results")

    # Export project data
    export_parser = subparsers.add_parser("export", help="Export project data")
    export_parser.add_argument("project_id", help="Project ID")
    export_parser.add_argument("--output-file", type=Path, required=True, help="Output JSON file")
    export_parser.add_argument("--include-content", action="store_true", help="Include extracted content")

    # Global options
    parser.add_argument(
        "--db-path",
        type=Path,
        default="rkb_documents.db",
        help="Path to document registry database (default: rkb_documents.db)"
    )


def execute(args: argparse.Namespace) -> int:
    """Execute the project command."""
    if not args.action:
        print("Error: No action specified. Use --help for available actions.")
        return 1

    try:
        # Initialize services
        registry = DocumentRegistry(args.db_path)
        project_service = ProjectService(registry)

        if args.action == "create":
            return _create_project(project_service, args)
        if args.action == "list":
            return _list_projects(project_service, args)
        if args.action == "show":
            return _show_project(project_service, args)
        if args.action == "find-pdfs":
            return _find_pdfs(project_service, args)
        if args.action == "subset":
            return _create_subset(project_service, args)
        if args.action == "export":
            return _export_project(project_service, args)
        print(f"Unknown action: {args.action}")
        return 1

    except Exception as e:
        print(f"✗ Project command failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def _create_project(service: ProjectService, args: argparse.Namespace) -> int:
    """Create a new project."""
    project_id = service.create_project(
        project_name=args.name,
        description=args.description or "",
        data_dir=args.data_dir
    )
    print(f"Project ID: {project_id}")
    return 0


def _list_projects(service: ProjectService, args: argparse.Namespace) -> int:
    """List all projects."""
    projects = service.list_projects()

    if not projects:
        print("No projects found.")
        return 0

    print("📁 Projects")
    print("=" * 50)
    for project_id, stats in projects.items():
        print(f"\nProject: {project_id}")
        print(f"  Total documents: {stats.total_documents}")
        print(f"  Indexed: {stats.indexed_count}")
        print(f"  Pending: {stats.pending_count}")
        print(f"  Failed: {stats.failed_count}")

    return 0


def _show_project(service: ProjectService, args: argparse.Namespace) -> int:
    """Show project details."""
    try:
        stats = service.get_project_stats(args.project_id)
        print(f"📁 Project: {args.project_id}")
        print("=" * 50)
        print(f"Total documents: {stats.total_documents}")
        print(f"Pending: {stats.pending_count}")
        print(f"Extracting: {stats.extracting_count}")
        print(f"Extracted: {stats.extracted_count}")
        print(f"Indexing: {stats.indexing_count}")
        print(f"Indexed: {stats.indexed_count}")
        print(f"Failed: {stats.failed_count}")
        print(f"Total chunks: {stats.total_chunks}")
        return 0
    except Exception as e:
        print(f"✗ Project not found or error: {e}")
        return 1


def _find_pdfs(service: ProjectService, args: argparse.Namespace) -> int:
    """Find recent PDFs."""
    try:
        files = service.find_recent_pdfs(
            data_dir=args.data_dir,
            num_files=args.num_files,
            output_file=args.output_file,
            project_id=args.project_id
        )

        print(f"\n📄 Found {len(files)} PDF files:")
        for i, file_info in enumerate(files[:20], 1):
            print(f"  {i:2d}. {file_info['name']} ({file_info['size_mb']:.1f} MB)")

        if len(files) > 20:
            print(f"  ... and {len(files) - 20} more files")

        return 0
    except Exception as e:
        print(f"✗ Error finding PDFs: {e}")
        return 1


def _create_subset(service: ProjectService, args: argparse.Namespace) -> int:
    """Create document subset."""
    criteria = {}

    if args.status:
        criteria["status"] = args.status
    if args.date_from:
        criteria["date_from"] = args.date_from
    if args.date_to:
        criteria["date_to"] = args.date_to
    if args.filename_pattern:
        criteria["filename_pattern"] = args.filename_pattern
    if args.limit:
        criteria["limit"] = args.limit

    try:
        subset = service.create_document_subset(
            subset_name=args.name,
            criteria=criteria,
            project_id=args.project_id
        )

        print(f"📋 Created subset '{args.name}' with {len(subset)} documents")
        return 0
    except Exception as e:
        print(f"✗ Error creating subset: {e}")
        return 1


def _export_project(service: ProjectService, args: argparse.Namespace) -> int:
    """Export project data."""
    try:
        result = service.export_project_data(
            project_id=args.project_id,
            output_file=args.output_file,
            include_content=args.include_content
        )

        print(f"📦 Exported {result['documents_exported']} documents")
        print(f"💾 File size: {result['file_size_kb']} KB")
        return 0
    except Exception as e:
        print(f"✗ Error exporting project: {e}")
        return 1
