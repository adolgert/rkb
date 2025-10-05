"""Search command - Perform semantic search over indexed documents."""
# ruff: noqa: T201

import argparse
from pathlib import Path

from rkb.core.document_registry import DocumentRegistry
from rkb.services.search_service import SearchService


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add command-specific arguments."""
    parser.add_argument(
        "query",
        nargs="*",
        help="Search query (if not provided, enters interactive mode)"
    )

    parser.add_argument(
        "--db-path",
        type=Path,
        default="rkb_documents.db",
        help="Path to document registry database (default: rkb_documents.db)"
    )

    parser.add_argument(
        "--vector-db-path",
        type=Path,
        default="rkb_chroma_db",
        help="Path to vector database (default: rkb_chroma_db)"
    )

    parser.add_argument(
        "--collection-name",
        default="documents",
        help="Vector database collection name (default: documents)"
    )

    parser.add_argument(
        "--embedder",
        choices=["chroma", "ollama"],
        default="chroma",
        help="Embedder to use (default: chroma)"
    )

    parser.add_argument(
        "--num-results", "-n",
        type=int,
        default=5,
        help="Number of results to return (default: 5)"
    )

    parser.add_argument(
        "--filter-equations",
        action="store_true",
        help="Filter to only show results with equations"
    )

    parser.add_argument(
        "--no-equations",
        action="store_true",
        help="Filter to exclude results with equations"
    )

    parser.add_argument(
        "--project-id",
        help="Filter to specific project"
    )

    parser.add_argument(
        "--document-ids",
        nargs="+",
        help="Filter to specific document IDs"
    )

    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Start interactive search mode"
    )

    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show database statistics"
    )


def execute(args: argparse.Namespace) -> int:
    """Execute the search command."""
    # Check if database exists
    if not args.vector_db_path.exists():
        print("✗ Vector database not found. Run 'rkb pipeline' or 'rkb index' first.")
        return 1

    try:
        # Initialize services
        registry = DocumentRegistry(args.db_path)
        search_service = SearchService(
            db_path=args.vector_db_path,
            collection_name=args.collection_name,
            embedder_name=args.embedder,
            registry=registry
        )

        # Handle stats request
        if args.stats:
            print("📊 Database Statistics")
            print("=" * 30)
            stats = search_service.get_database_stats()
            print(f"Total chunks: {stats.get('total_chunks', 0):,}")
            print(f"Equation percentage: {stats.get('equation_percentage', 0):.1f}%")
            print(f"Collection: {stats.get('collection_name', 'N/A')}")
            if "registry_stats" in stats:
                reg_stats = stats["registry_stats"]
                print(f"Documents in registry: {reg_stats.get('total_documents', 0)}")
            return 0

        # Determine search mode
        if args.query:
            # Single query mode
            query = " ".join(args.query)
            return _perform_search(search_service, query, args)
        if args.interactive:
            # Interactive mode
            return _interactive_search(search_service, args)
        # No query provided, default to interactive mode
        print("🔍 Interactive Search Mode")
        print("Type your queries (press Ctrl+C to exit)")
        print()
        return _interactive_search(search_service, args)

    except Exception as e:
        print(f"✗ Search failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def _perform_search(search_service: SearchService, query: str, args: argparse.Namespace) -> int:
    """Perform a single search."""
    # Set up filters
    filter_equations = None
    if args.filter_equations:
        filter_equations = True
    elif args.no_equations:
        filter_equations = False

    # Perform search
    result = search_service.search_documents(
        query=query,
        n_results=args.num_results,
        filter_equations=filter_equations,
        project_id=getattr(args, "project_id", None),
        document_ids=getattr(args, "document_ids", None)
    )

    # Display results
    search_service.display_results(result)

    return 0 if result.total_results > 0 else 1


def _interactive_search(search_service: SearchService, args: argparse.Namespace) -> int:
    """Run interactive search mode."""
    try:
        while True:
            try:
                query = input("🔍 Query: ").strip()
                if not query:
                    continue

                # Handle special commands
                if query.lower() in ["exit", "quit", "q"]:
                    break
                if query.lower() in ["help", "h"]:
                    _show_help()
                    continue
                if query.lower() == "stats":
                    stats = search_service.get_database_stats()
                    print(f"📊 Total chunks: {stats.get('total_chunks', 0):,}")
                    print(f"📈 Equation percentage: {stats.get('equation_percentage', 0):.1f}%")
                    continue

                # Perform search
                _perform_search(search_service, query, args)
                print()

            except EOFError:
                break

        print("👋 Search session ended")
        return 0

    except KeyboardInterrupt:
        print("\n👋 Search session ended")
        return 0


def _show_help() -> None:
    """Show interactive mode help."""
    print("""
Interactive Search Commands:
  <query>     - Search for documents matching query
  help, h     - Show this help message
  stats       - Show database statistics
  exit, quit  - Exit interactive mode
    """)
