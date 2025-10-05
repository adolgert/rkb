"""Documents command - Search for documents using document-level ranking."""
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
        default=10,
        help="Number of documents to return (default: 10)"
    )

    parser.add_argument(
        "--metric",
        choices=["similarity", "relevance"],
        default="relevance",
        help="Ranking metric: 'similarity' (max pooling) or 'relevance' (hit counting, default)"
    )

    parser.add_argument(
        "--threshold",
        type=float,
        help="Minimum similarity threshold (default: from embedder)"
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
    """Execute the documents search command."""
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
        print("🔍 Interactive Document Search Mode")
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
    """Perform a single document-level search."""
    # Set up filters
    filter_equations = None
    if args.filter_equations:
        filter_equations = True
    elif args.no_equations:
        filter_equations = False

    # Perform document-level search
    ranked_docs, all_chunks, stats = search_service.search_documents_ranked(
        query=query,
        n_docs=args.num_results,
        metric=args.metric,
        min_threshold=args.threshold,
        filter_equations=filter_equations,
        project_id=args.project_id,
    )

    # Display results
    _display_results(
        search_service=search_service,
        query=query,
        ranked_docs=ranked_docs,
        all_chunks=all_chunks,
        stats=stats,
        metric=args.metric,
    )

    return 0 if ranked_docs else 1


def _display_results(
    search_service: SearchService,
    query: str,
    ranked_docs: list,
    all_chunks: list,
    stats: dict,
    metric: str,
) -> None:
    """Display document search results."""
    if not ranked_docs:
        print("No results found.")
        return

    # Header
    print(f"\n📊 Found {len(ranked_docs)} documents for: '{query}'")
    chunks_msg = f"Fetched {stats['chunks_fetched']} chunks in {stats['iterations']} iteration(s)"
    print(f"📈 Metric: {metric} | {chunks_msg}")
    print("=" * 80)

    # Get both metrics for display
    similarity_scores = search_service.rank_by_similarity(all_chunks)
    relevance_scores = search_service.rank_by_relevance(
        all_chunks,
        search_service.embedder.minimum_threshold
    )

    # Create lookup dicts
    similarity_lookup = {doc.doc_id: doc for doc in similarity_scores}
    relevance_lookup = {doc.doc_id: doc for doc in relevance_scores}

    # Display each result
    for i, doc_score in enumerate(ranked_docs, 1):
        # Get display data (best chunk)
        display_data = search_service.get_display_data(doc_score, all_chunks, strategy="top_chunk")

        # Get both metric values
        sim_score = similarity_lookup.get(doc_score.doc_id)
        rel_score = relevance_lookup.get(doc_score.doc_id)

        sim_value = sim_score.score if sim_score else 0.0
        rel_value = int(rel_score.score) if rel_score else 0

        # Get document metadata from registry
        doc_metadata = search_service.registry.get_document(doc_score.doc_id)

        # Print result header with both metrics
        print(f"\n🔖 Result {i}")
        print(f"   Relevance: {rel_value} hits | Similarity: {sim_value:.3f}")

        # Print document info
        if doc_metadata:
            # Get document name from source_path or title
            if doc_metadata.source_path:
                doc_name = doc_metadata.source_path.name
                doc_path = str(doc_metadata.source_path)
            else:
                doc_name = doc_metadata.title or "Unknown"
                doc_path = ""

            print(f"📄 Document: {doc_name}")
            if doc_path:
                # Get page numbers from best chunk
                pages = display_data.get("page_numbers", [])
                page_str = f"#page={pages[0]}" if pages else ""
                file_link = f"file://{doc_path}{page_str}"
                print(f"🔗 Link: {file_link}")
        else:
            print(f"📄 Document ID: {doc_score.doc_id}")

        # Print best chunk preview
        chunk_text = display_data.get("chunk_text", "")
        if chunk_text:
            preview = chunk_text[:200]
            if len(chunk_text) > 200:
                preview += "..."
            print(f"📝 Preview:\n   {preview}")

        print("-" * 80)

    # Show statistics
    print("\n📈 Search Statistics:")
    print(f"   Documents found: {len(ranked_docs)}")
    print(f"   Chunks fetched: {stats['chunks_fetched']}")
    print(f"   Chunks above threshold: {stats['chunks_above_threshold']}")
    print(f"   Iterations: {stats['iterations']}")


def _interactive_search(search_service: SearchService, args: argparse.Namespace) -> int:
    """Run interactive document search mode."""
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
Interactive Document Search Commands:
  <query>     - Search for documents matching query
  help, h     - Show this help message
  stats       - Show database statistics
  exit, quit  - Exit interactive mode
    """)
