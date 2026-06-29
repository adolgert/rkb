"""Backfill chunk_count in rkb_documents.db from Chroma.

Counts chunks per doc_id in the Chroma collection and writes the totals
into the chunk_count column of rkb_documents.db.

Usage:
    uv run python backfill_chunk_counts.py [--dry-run]
"""
# ruff: noqa: T201

import argparse
import sqlite3


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report without writing")
    args = parser.parse_args()

    from rkb.collection.config import CollectionConfig

    config = CollectionConfig.load(None)
    sha256_dir = config.library_root / "sha256"
    chroma_path = sha256_dir / "rkb_chroma_db"
    db_path = sha256_dir / "rkb_documents.db"

    print(f"Chroma: {chroma_path}")
    print(f"DB:     {db_path}")

    import chromadb

    client = chromadb.PersistentClient(path=str(chroma_path))
    try:
        collection = client.get_collection("documents")
    except Exception as exc:
        print(f"Could not open Chroma collection: {exc}")
        return

    total = collection.count()
    print(f"Total chunks in Chroma: {total:,}")

    # Count chunks per doc_id by fetching in batches
    doc_counts: dict[str, int] = {}
    batch_size = 5000
    offset = 0
    while offset < total:
        batch = collection.get(
            limit=batch_size,
            offset=offset,
            include=["metadatas"],
        )
        if not batch["metadatas"]:
            break
        for meta in batch["metadatas"]:
            doc_id = meta.get("doc_id") if meta else None
            if doc_id:
                doc_counts[doc_id] = doc_counts.get(doc_id, 0) + 1
        offset += len(batch["metadatas"])
        print(f"  Scanned {offset:,} / {total:,} chunks ...", end="\r")

    print(f"\nFound {len(doc_counts):,} distinct documents in Chroma.")

    if args.dry_run:
        for doc_id, count in sorted(doc_counts.items())[:20]:
            print(f"  {doc_id[:16]}...  {count} chunks")
        if len(doc_counts) > 20:
            print(f"  ... and {len(doc_counts) - 20} more")
        return

    # Write to SQLite
    con = sqlite3.connect(str(db_path))
    # Ensure column exists (migration for older DBs)
    import contextlib
    with contextlib.suppress(sqlite3.OperationalError):
        con.execute("ALTER TABLE documents ADD COLUMN chunk_count INTEGER")
    con.commit()
    updated = 0
    try:
        for doc_id, count in doc_counts.items():
            cur = con.execute(
                "UPDATE documents SET chunk_count = ? WHERE doc_id = ?",
                (count, doc_id),
            )
            if cur.rowcount > 0:
                updated += 1
        con.commit()
    finally:
        con.close()

    print(f"Updated chunk_count for {updated:,} documents in {db_path}.")
    no_record = len(doc_counts) - updated
    if no_record:
        print(f"  {no_record} doc_ids from Chroma had no matching row in rkb_documents.db.")


if __name__ == "__main__":
    main()
