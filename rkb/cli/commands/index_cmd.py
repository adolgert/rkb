"""Index command - Create embeddings and index documents for search."""

import argparse
from pathlib import Path

from rkb.core.document_registry import DocumentRegistry
from rkb.core.models import DocumentStatus
from rkb.pipelines.complete_pipeline import CompletePipeline


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add command-specific arguments."""
    parser.add_argument(
        "--embedder",
        choices=["chroma", "ollama"],
        default="chroma",
        help="Embedder to use (default: chroma)"
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
        "--project-id",
        help="Index only documents from specific project"
    )

    parser.add_argument(
        "--force-reindex",
        action="store_true",
        help="Force reindexing of existing embeddings"
    )

    parser.add_argument(
        "--db-path",
        type=Path,
        default="rkb_documents.db",
        help="Path to document registry database (default: rkb_documents.db)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be indexed without actually indexing"
    )


def execute(args: argparse.Namespace) -> int:
    """Execute the index command."""
    try:
        print("🔗 RKB Document Indexing")
        print("=" * 30)
        print(f"⚙️  Embedder: {args.embedder}")
        print(f"📁 Vector DB: {args.vector_db_path}")
        print(f"🔄 Force reindex: {args.force_reindex}")
        print(f"🧪 Dry run: {args.dry_run}")
        print()

        # Initialize services
        registry = DocumentRegistry(args.db_path)

        # Find documents ready for indexing
        if args.project_id:
            from rkb.services.project_service import ProjectService
            project_service = ProjectService(registry)
            documents = project_service.get_project_documents(
                args.project_id,
                DocumentStatus.EXTRACTED
            )
        else:
            documents = registry.get_documents_by_status(DocumentStatus.EXTRACTED)

        if not documents:
            print("✗ No extracted documents found for indexing.")
            print("  Run 'rkb extract' or 'rkb pipeline' first.")
            return 1

        print(f"📄 Found {len(documents)} documents ready for indexing")

        if args.dry_run:
            print("\n🔍 Documents that would be indexed:")
            for i, doc in enumerate(documents[:10], 1):
                name = doc.source_path.name if doc.source_path else doc.doc_id
                print(f"  {i:2d}. {name}")
            if len(documents) > 10:
                print(f"  ... and {len(documents) - 10} more documents")
            return 0

        # Initialize pipeline for embedding
        pipeline = CompletePipeline(
            registry=registry,
            extractor_name="nougat",  # Not used for indexing-only
            embedder_name=args.embedder,
            project_id=args.project_id
        )

        # Extract paths for indexing
        pdf_paths = [doc.source_path for doc in documents if doc.source_path]

        if not pdf_paths:
            print("✗ No valid source paths found for documents")
            return 1

        # Run embedding pipeline
        results = pipeline.process_documents(
            pdf_paths=pdf_paths,
            project_id=args.project_id,
            force_reprocess=args.force_reindex,
            skip_extraction=True  # Only do embedding
        )

        # Display results
        print("\n" + "=" * 50)
        print("🎉 INDEXING COMPLETED")
        print("=" * 50)
        print(f"📄 Documents processed: {results['documents_processed']}")
        print(f"🔗 Successfully indexed: {results['successful_embeddings']}")
        print(f"❌ Failed indexing: {results['failed_embeddings']}")

        if results["successful_embeddings"] > 0:
            print("\n🔍 Ready for semantic search!")
            print('   Run: rkb search "your query here"')

        return 0

    except Exception as e:
        print(f"✗ Index command failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1
