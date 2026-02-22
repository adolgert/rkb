"""Remove command - Delete a PDF and all associated data from the system."""
# ruff: noqa: T201

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from rkb.collection.canonical_store import canonical_dir
from rkb.collection.catalog import Catalog
from rkb.collection.config import CollectionConfig

if TYPE_CHECKING:
    import argparse


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add command-specific arguments."""
    parser.add_argument(
        "target",
        nargs="+",
        metavar="TITLE_OR_HASH",
        help="Title fragment or sha256 hash (prefix ≥6 chars) to identify the PDF",
    )

    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Skip confirmation prompt",
    )

    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Path to rkb_documents.db (default: <library>/sha256/rkb_documents.db)",
    )

    parser.add_argument(
        "--vector-db-path",
        type=Path,
        default=None,
        help="Path to Chroma vector DB (default: <library>/sha256/rkb_chroma_db)",
    )

    parser.add_argument(
        "--collection-name",
        default="documents",
        help="Chroma collection name (default: documents)",
    )


def _search_catalog(catalog: Catalog, target: str) -> list[dict]:
    """Search canonical_files for rows matching target (hash or title fragment)."""
    conn = catalog._connect()  # noqa: SLF001

    if len(target) == 64 and all(c in "0123456789abcdefABCDEF" for c in target):
        # Exact sha256 match
        rows = conn.execute(
            "SELECT * FROM canonical_files WHERE content_sha256 = ?",
            (target.lower(),),
        ).fetchall()
    elif len(target) >= 6 and all(c in "0123456789abcdefABCDEF" for c in target):
        # Prefix sha256 match
        rows = conn.execute(
            "SELECT * FROM canonical_files WHERE content_sha256 LIKE ?",
            (target.lower() + "%",),
        ).fetchall()
    else:
        # Case-insensitive title fragment match
        rows = conn.execute(
            "SELECT * FROM canonical_files WHERE display_name LIKE ? COLLATE NOCASE",
            (f"%{target}%",),
        ).fetchall()

    return [dict(row) for row in rows]


def _print_disambiguation(matches: list[dict]) -> None:
    """Print a table of matches for disambiguation."""
    print(f"Found {len(matches)} matching PDFs:\n")
    header = f"  {'display_name':<50}  {'sha256':<18}  {'size':>10}  {'pages':>5}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for row in matches:
        name = row.get("display_name", "")[:50]
        sha = row.get("content_sha256", "")[:16] + "..."
        size = row.get("file_size_bytes") or 0
        pages = row.get("page_count") or "?"
        size_str = f"{size:,}" if size else "?"
        print(f"  {name:<50}  {sha:<18}  {size_str:>10}  {pages!s:>5}")


def _delete_from_documents_db(db_path: Path, content_hash: str) -> int:
    """Delete embeddings, extractions, and documents by content_hash. Returns doc count."""
    if not db_path.exists():
        return 0

    with sqlite3.connect(db_path) as conn:
        # Find doc_ids matching this content hash
        rows = conn.execute(
            "SELECT doc_id FROM documents WHERE content_hash = ?",
            (content_hash,),
        ).fetchall()
        doc_ids = [row[0] for row in rows]

        if not doc_ids:
            return 0

        placeholders = ",".join("?" * len(doc_ids))

        conn.execute(
            f"DELETE FROM embeddings WHERE doc_id IN ({placeholders})",
            doc_ids,
        )
        conn.execute(
            f"DELETE FROM extractions WHERE doc_id IN ({placeholders})",
            doc_ids,
        )
        conn.execute(
            f"DELETE FROM documents WHERE doc_id IN ({placeholders})",
            doc_ids,
        )

    return len(doc_ids)


def _delete_from_catalog(catalog: Catalog, content_sha256: str) -> None:
    """Delete all catalog rows for a content hash (in FK-safe order)."""
    conn = catalog._connect()  # noqa: SLF001

    conn.execute(
        "DELETE FROM metadata_resolved WHERE content_sha256 = ?",
        (content_sha256,),
    )
    conn.execute(
        "DELETE FROM metadata_sources WHERE content_sha256 = ?",
        (content_sha256,),
    )
    conn.execute(
        "DELETE FROM zotero_links WHERE content_sha256 = ?",
        (content_sha256,),
    )
    conn.execute(
        "DELETE FROM source_sightings WHERE content_sha256 = ?",
        (content_sha256,),
    )
    conn.execute(
        "DELETE FROM ingest_log WHERE content_sha256 = ?",
        (content_sha256,),
    )
    conn.execute(
        "DELETE FROM canonical_files WHERE content_sha256 = ?",
        (content_sha256,),
    )
    conn.commit()


def _delete_from_chroma(vector_db_path: Path, collection_name: str, sha256: str) -> int:
    """Delete all chunks for a document from Chroma. Returns chunk count deleted."""
    if not vector_db_path.exists():
        return 0
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(vector_db_path))
        collection = client.get_collection(collection_name)
        results = collection.get(where={"doc_id": sha256}, include=[])
        if results["ids"]:
            collection.delete(ids=results["ids"])
            return len(results["ids"])
    except Exception as error:
        print(f"  Warning: could not remove Chroma chunks: {error}")
    return 0


def _clean_empty_parents(path: Path) -> None:
    """Remove up to two empty ancestor directories (the AA/BB/ intermediates)."""
    for _ in range(2):
        parent = path.parent
        if not parent.exists():
            path = parent
            continue
        try:
            if not any(parent.iterdir()):
                parent.rmdir()
        except OSError:
            break
        path = parent


def execute(args: argparse.Namespace) -> int:
    """Execute the remove command."""
    target = " ".join(args.target)

    try:
        config = CollectionConfig.load(config_path=getattr(args, "config", None))
    except Exception as error:
        print(f"Failed to load config: {error}")
        return 1

    sha256_dir = config.library_root / "sha256"
    if args.db_path is None:
        args.db_path = sha256_dir / "rkb_documents.db"
    if args.vector_db_path is None:
        args.vector_db_path = sha256_dir / "rkb_chroma_db"

    catalog = Catalog(config.catalog_db)
    catalog.initialize()

    try:
        matches = _search_catalog(catalog, target)
    except Exception as error:
        catalog.close()
        print(f"Search failed: {error}")
        return 1

    if not matches:
        catalog.close()
        print("No matching PDFs found.")
        return 1

    if len(matches) > 1:
        _print_disambiguation(matches)
        print("\nRefine your query or use the sha256 prefix.")
        catalog.close()
        return 1

    record = matches[0]
    sha256 = record["content_sha256"]
    display_name = record.get("display_name", sha256)
    size = record.get("file_size_bytes") or 0
    pages = record.get("page_count") or "?"

    hash_dir = canonical_dir(config.library_root, sha256)

    print(f"  Name:   {display_name}")
    print(f"  Hash:   {sha256}")
    print(f"  Path:   {hash_dir}")
    print(f"  Size:   {size:,} bytes" if size else "  Size:   unknown")
    print(f"  Pages:  {pages}")

    if not args.force:
        try:
            answer = input("\nDelete? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            catalog.close()
            return 130
        if answer != "y":
            print("Aborted.")
            catalog.close()
            return 0

    # 1. Delete from rkb_documents.db
    doc_count = _delete_from_documents_db(args.db_path, sha256)

    # 2. Delete from pdf_catalog.db
    _delete_from_catalog(catalog, sha256)
    catalog.close()

    # 3. Delete from Chroma vector DB
    chunk_count = _delete_from_chroma(args.vector_db_path, args.collection_name, sha256)

    # 4. Delete filesystem directory
    if hash_dir.exists():
        shutil.rmtree(hash_dir)
        _clean_empty_parents(hash_dir)

    print(f"Removed: {display_name} ({sha256[:16]}...)")
    if doc_count:
        print(f"  Deleted {doc_count} document registry record(s).")
    if chunk_count:
        print(f"  Deleted {chunk_count} Chroma chunk(s).")

    return 0
