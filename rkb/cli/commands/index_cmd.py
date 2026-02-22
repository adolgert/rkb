"""Index command - Create embeddings and index documents for search."""
# ruff: noqa: T201

import argparse
import contextlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


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
        default=None,
        help="Path to vector database (default: <library>/sha256/rkb_chroma_db)"
    )

    parser.add_argument(
        "--collection-name",
        default="documents",
        help="Vector database collection name (default: documents)"
    )

    parser.add_argument(
        "--force-reindex",
        action="store_true",
        help="Force reindexing of existing embeddings"
    )

    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Path to document registry database (default: <library>/sha256/rkb_documents.db)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be indexed without actually indexing"
    )


def execute(args: argparse.Namespace) -> int:  # noqa: PLR0912
    """Execute the index command."""
    try:
        from rkb.collection.config import CollectionConfig
        config = CollectionConfig.load(getattr(args, "config", None))
        sha256_dir = config.library_root / "sha256"
        if args.vector_db_path is None:
            args.vector_db_path = sha256_dir / "rkb_chroma_db"
        if args.db_path is None:
            args.db_path = sha256_dir / "rkb_documents.db"

        rebuild = getattr(args, "rebuild", False)
        verbose = getattr(args, "verbose", False)

        print("RKB Document Indexing")
        print("=" * 30)
        print(f"Embedder: {args.embedder}")
        print(f"Vector DB: {args.vector_db_path}")
        print(f"Force reindex: {args.force_reindex}")
        print(f"Rebuild (wipe): {rebuild}")
        print(f"Dry run: {args.dry_run}")
        print()

        # Handle rebuild: wipe existing Chroma collection and BM25 files
        if rebuild and not args.dry_run:
            _wipe_index(args.vector_db_path, args.collection_name)
            print("Existing index wiped.")
            print()

        # Load config and catalog
        from rkb.collection.canonical_store import canonical_dir
        from rkb.collection.catalog import Catalog
        from rkb.collection.config import CollectionConfig

        config = CollectionConfig.load(getattr(args, "config", None))
        catalog = Catalog(config.catalog_db)
        catalog.initialize()

        hashes = catalog.list_canonical_hashes()
        if not hashes:
            print("No canonical files found in catalog.")
            return 1

        print(f"Found {len(hashes)} canonical files in catalog.")

        # Collect files to index
        to_index = []
        no_md_count = 0

        for sha256 in hashes:
            row = catalog.get_canonical_file(sha256)
            display_name = row["display_name"] if row else sha256[:16]
            hash_dir = canonical_dir(config.library_root, sha256)
            mds = sorted(hash_dir.glob("extractions/marker-pdf-*/extracted.md"))
            if not mds:
                mds = sorted(hash_dir.glob("extractions/nougat-ocr-*/extracted.mmd"))
            if not mds:
                no_md_count += 1
                if verbose:
                    print(f"  Skip (no extracted.md): {display_name}")
                continue
            to_index.append((sha256, display_name, mds[-1]))

        if not to_index:
            print("No documents with extracted.md found.")
            if no_md_count:
                print(f"  {no_md_count} documents have no extracted.md. Run 'rkb translate' first.")
            return 1

        if args.dry_run:
            print(f"\nDry run: would index {len(to_index)} documents:")
            for sha256, display_name, _md_path in to_index[:10]:
                print(f"  {sha256[:12]}... {display_name}")
            if len(to_index) > 10:
                print(f"  ... and {len(to_index) - 10} more")
            print(f"\n  {no_md_count} documents skipped (no extracted.md)")
            return 0

        # Get chroma collection for already-indexed check
        import chromadb

        chroma_client = chromadb.PersistentClient(path=str(args.vector_db_path))
        try:
            chroma_collection = chroma_client.get_collection(args.collection_name)
        except Exception:
            chroma_collection = None

        # Initialize embedder
        from rkb.embedders import get_embedder

        embedder = get_embedder(
            args.embedder,
            collection_name=args.collection_name,
            db_path=args.vector_db_path,
        )

        from rkb.core.text_processing import chunk_text_by_sections

        indexed_count = 0
        skipped_already_count = 0

        for sha256, display_name, md_path in to_index:
            # Skip if already indexed (unless force-reindex)
            if (
                not args.force_reindex
                and chroma_collection is not None
                and _already_indexed(chroma_collection, sha256)
            ):
                skipped_already_count += 1
                if verbose:
                    print(f"  Skip (already indexed): {display_name}")
                continue

            # Chunk
            content = md_path.read_text(encoding="utf-8")
            chunks = chunk_text_by_sections(content)
            if not chunks:
                if verbose:
                    print(f"  Skip (no chunks): {display_name}")
                continue

            chunk_texts = [c for c, _ in chunks]
            metadatas = [
                {
                    "doc_id": sha256,
                    "pdf_name": display_name,
                    "chunk_index": i,
                    "page_numbers": "",
                    "has_equations": False,
                }
                for i, (c, _) in enumerate(chunks)
            ]

            result = embedder.embed(chunk_texts, metadatas)
            if result.error_message:
                print(f"  Warning: embedding failed for {display_name}: {result.error_message}")
                continue

            # Mirror to rkb_documents.db for search/documents compatibility
            _upsert_document_record(args.db_path, sha256, display_name, str(md_path))
            indexed_count += 1

            if verbose:
                print(f"  Indexed {len(chunk_texts)} chunks: {display_name}")

        print()
        print(f"Indexed: {indexed_count}")
        print(f"Skipped (already indexed): {skipped_already_count}")
        print(f"Skipped (no extracted.md): {no_md_count}")

        if indexed_count > 0:
            _build_bm25(args.vector_db_path, args.collection_name)
            print("\nReady for hybrid search!")
            print('   Run: rkb search "your query here"')

        return 0

    except Exception as e:
        print(f"Index command failed: {e}")
        if getattr(args, "verbose", False):
            import traceback
            traceback.print_exc()
        return 1


def _already_indexed(collection, sha256: str) -> bool:
    """Return True if any chunk with doc_id == sha256 exists in Chroma."""
    try:
        result = collection.get(where={"doc_id": sha256}, limit=1)
        return len(result["ids"]) > 0
    except Exception:
        return False


def _upsert_document_record(
    db_path: Path, sha256: str, title: str, source_path: str
) -> None:
    """Upsert a document record into rkb_documents.db for search/documents compat."""
    now = datetime.now(UTC).isoformat()
    con = sqlite3.connect(str(db_path))
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                doc_id TEXT PRIMARY KEY,
                source_path TEXT,
                content_hash TEXT,
                title TEXT,
                authors TEXT,
                arxiv_id TEXT,
                doi TEXT,
                version INTEGER DEFAULT 1,
                status TEXT,
                added_date TEXT,
                updated_date TEXT,
                project_id TEXT
            )
            """
        )
        # Add project_id to tables created before this column existed
        with contextlib.suppress(sqlite3.OperationalError):
            con.execute("ALTER TABLE documents ADD COLUMN project_id TEXT")
        con.execute(
            """
            INSERT INTO documents (
                doc_id, source_path, content_hash, title, status, added_date, updated_date
            )
            VALUES (?, ?, ?, ?, 'extracted', ?, ?)
            ON CONFLICT(doc_id) DO UPDATE SET
                source_path=excluded.source_path,
                title=excluded.title,
                status='extracted',
                updated_date=excluded.updated_date
            """,
            (sha256, source_path, sha256, title, now, now),
        )
        con.commit()
    finally:
        con.close()


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

    print("\nBuilding BM25 keyword index...")
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
