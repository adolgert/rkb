"""One-time migration: update stale pdf_name in Chroma from the catalog.

For each chunk in the Chroma collection, looks up the current display_name
from pdf_catalog.db by doc_id (sha256) and updates pdf_name if it differs.

Run from the directory containing rkb_chroma_db:

    uv run python /path/to/migrate_chroma_pdf_names.py [--dry-run]
"""

import argparse
import sqlite3
import sys
from pathlib import Path


def load_catalog_names(catalog_db: Path) -> dict[str, str]:
    """Return {sha256: display_name} for all entries in the catalog."""
    with sqlite3.connect(str(catalog_db)) as conn:
        rows = conn.execute(
            "SELECT content_sha256, display_name FROM canonical_files"
        ).fetchall()
    return {sha256: display_name for sha256, display_name in rows}


def migrate(
    chroma_path: Path,
    catalog_db: Path,
    collection_name: str = "documents",
    dry_run: bool = False,
) -> None:
    import chromadb

    print(f"Catalog:    {catalog_db}")
    print(f"Chroma DB:  {chroma_path}")
    print(f"Collection: {collection_name}")
    print(f"Dry run:    {dry_run}")
    print()

    catalog = load_catalog_names(catalog_db)
    print(f"Catalog entries: {len(catalog)}")

    client = chromadb.PersistentClient(path=str(chroma_path))
    collection = client.get_collection(collection_name)
    total_chunks = collection.count()
    print(f"Total chunks:    {total_chunks}")
    print()

    batch_size = 5000
    offset = 0
    to_update_ids: list[str] = []
    to_update_metadatas: list[dict] = []
    stale = 0
    missing = 0

    while offset < total_chunks:
        batch = collection.get(
            limit=batch_size,
            offset=offset,
            include=["metadatas"],
        )
        if not batch["metadatas"]:
            break

        for chunk_id, meta in zip(batch["ids"], batch["metadatas"]):
            doc_id = meta.get("doc_id")
            current_pdf_name = meta.get("pdf_name", "")
            current_name = catalog.get(doc_id)

            if current_name is None:
                missing += 1
                continue

            if current_pdf_name != current_name:
                stale += 1
                updated_meta = dict(meta)
                updated_meta["pdf_name"] = current_name
                to_update_ids.append(chunk_id)
                to_update_metadatas.append(updated_meta)

        offset += len(batch["ids"])
        print(f"  Scanned {offset}/{total_chunks} chunks...", end="\r")

    print()
    print(f"Stale chunks to update: {stale}")
    print(f"Chunks with no catalog entry: {missing}")

    if not to_update_ids:
        print("Nothing to update.")
        return

    if dry_run:
        print("Dry run — no changes written.")
        # Show a sample
        for chunk_id, meta in zip(to_update_ids[:5], to_update_metadatas[:5]):
            doc_id = meta.get("doc_id", "")
            old_name = collection.get(ids=[chunk_id], include=["metadatas"])["metadatas"][0].get("pdf_name", "")
            print(f"  {doc_id[:12]}...  {old_name!r}  ->  {meta['pdf_name']!r}")
        return

    # Write updates in batches
    write_batch = 500
    for i in range(0, len(to_update_ids), write_batch):
        ids_batch = to_update_ids[i : i + write_batch]
        meta_batch = to_update_metadatas[i : i + write_batch]
        collection.update(ids=ids_batch, metadatas=meta_batch)
        print(f"  Updated {min(i + write_batch, len(to_update_ids))}/{len(to_update_ids)} chunks...", end="\r")

    print()
    print(f"Done. Updated {len(to_update_ids)} chunks.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--chroma-path",
        type=Path,
        default=Path("rkb_chroma_db"),
        help="Path to Chroma DB (default: rkb_chroma_db)",
    )
    parser.add_argument(
        "--catalog-db",
        type=Path,
        default=Path.home() / "Dropbox/findpdfs-library/db/pdf_catalog.db",
        help="Path to pdf_catalog.db",
    )
    parser.add_argument(
        "--collection-name",
        default="documents",
        help="Chroma collection name (default: documents)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing anything",
    )
    args = parser.parse_args()

    if not args.chroma_path.exists():
        print(f"Error: Chroma DB not found at {args.chroma_path}", file=sys.stderr)
        sys.exit(1)
    if not args.catalog_db.exists():
        print(f"Error: catalog DB not found at {args.catalog_db}", file=sys.stderr)
        sys.exit(1)

    migrate(
        chroma_path=args.chroma_path,
        catalog_db=args.catalog_db,
        collection_name=args.collection_name,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
