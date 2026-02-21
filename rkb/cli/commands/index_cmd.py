"""Index command - Create embeddings and index documents for search."""
# ruff: noqa: T201

import argparse
from pathlib import Path

from rkb.core.document_registry import DocumentRegistry
from rkb.core.models import DocumentStatus
from rkb.pipelines.complete_pipeline import CompletePipeline


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add command-specific arguments."""
    parser.add_argument(
        "--embedder",
        choices=["chroma", "ollama", "specter2"],
        default="specter2",
        help="Embedder to use (default: specter2)"
    )

    parser.add_argument(
        "--rebuild",
        action="store_true",
        help=(
            "Wipe and re-index everything (Chroma collection + BM25). "
            "Required to rebuild from scratch — guards against accidental data loss."
        ),
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

    parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        help="Directory for checkpoint files (default: .checkpoints)"
    )

    parser.add_argument(
        "--extraction-dir",
        type=Path,
        default=Path("rkb_extractions"),
        help="Directory for extraction output (default: rkb_extractions)"
    )


def execute(args: argparse.Namespace) -> int:
    """Execute the index command."""
    try:
        rebuild = getattr(args, "rebuild", False)

        print("🔗 RKB Document Indexing")
        print("=" * 30)
        print(f"⚙️  Embedder: {args.embedder}")
        print(f"📁 Vector DB: {args.vector_db_path}")
        print(f"🔄 Force reindex: {args.force_reindex}")
        print(f"🔁 Rebuild (wipe): {rebuild}")
        print(f"🧪 Dry run: {args.dry_run}")
        print()

        # Handle rebuild: wipe existing Chroma collection and BM25 files
        if rebuild and not args.dry_run:
            _wipe_index(args.vector_db_path, args.collection_name)
            print("🗑️  Existing index wiped.")
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

        # Determine checkpoint directory
        checkpoint_dir = (
            args.checkpoint_dir
            if hasattr(args, "checkpoint_dir") and args.checkpoint_dir
            else None
        )

        # Initialize pipeline for embedding
        pipeline = CompletePipeline(
            registry=registry,
            extractor_name="nougat",  # Not used for indexing-only
            embedder_name=args.embedder,
            project_id=args.project_id,
            checkpoint_dir=checkpoint_dir,
            extraction_dir=args.extraction_dir,
            vector_db_path=args.vector_db_path
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
            # Build BM25 index from the indexed chunks
            _build_bm25(args.vector_db_path, args.collection_name)
            print("\n🔍 Ready for hybrid search!")
            print('   Run: rkb search "your query here"')

        return 0

    except Exception as e:
        print(f"✗ Index command failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def _wipe_index(vector_db_path: Path, collection_name: str) -> None:
    """Delete the Chroma collection and BM25 index files."""
    import contextlib

    import chromadb

    from rkb.services.bm25_index import BM25Index

    # Remove Chroma collection
    if vector_db_path.exists():
        with contextlib.suppress(Exception):
            client = chromadb.PersistentClient(path=str(vector_db_path))
            with contextlib.suppress(Exception):
                client.delete_collection(collection_name)

    # Remove BM25 files
    BM25Index(vector_db_path).wipe()


def _build_bm25(vector_db_path: Path, collection_name: str) -> None:
    """Build BM25 index from the current contents of the Chroma collection."""
    import chromadb

    from rkb.services.bm25_index import BM25Index

    print("\n📝 Building BM25 keyword index...")
    try:
        client = chromadb.PersistentClient(path=str(vector_db_path))
        collection = client.get_collection(collection_name)
        total = collection.count()
        if total == 0:
            print("   No chunks found — BM25 index skipped.")
            return

        # Fetch all chunks (id + document text)
        batch_size = 5000
        chunk_pairs: list[tuple[str, str]] = []
        offset = 0
        while offset < total:
            batch = collection.get(
                limit=batch_size,
                offset=offset,
                include=["documents"],
            )
            if not batch["documents"]:
                break
            for cid, doc in zip(batch["ids"], batch["documents"], strict=True):
                chunk_pairs.append((cid, doc))
            offset += len(batch["ids"])

        bm25 = BM25Index(vector_db_path)
        bm25.build(chunk_pairs)
        print(f"   BM25 index built with {len(chunk_pairs):,} chunks.")
    except Exception as exc:
        print(f"   Warning: BM25 index build failed: {exc}")
