"""Backfill rkb_chunks.db from the Chroma 'documents' collection.

Reads all chunk text and metadata from Chroma and writes them into
the SQLite chunk store at <library>/sha256/rkb_chunks.db.

Usage:
    uv run python backfill_chunks_db.py [--dry-run]
"""
# ruff: noqa: T201

import argparse
from collections import defaultdict


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report without writing")
    args = parser.parse_args()

    from rkb.collection.config import CollectionConfig

    config = CollectionConfig.load(None)
    sha256_dir = config.library_root / "sha256"
    chroma_path = sha256_dir / "rkb_chroma_db"
    chunks_db_path = sha256_dir / "rkb_chunks.db"

    print(f"Chroma:    {chroma_path}")
    print(f"ChunksDB:  {chunks_db_path}")

    import chromadb

    client = chromadb.PersistentClient(path=str(chroma_path))
    try:
        collection = client.get_collection("documents")
    except Exception as exc:
        print(f"Could not open Chroma collection: {exc}")
        return

    total = collection.count()
    print(f"Total chunks in Chroma: {total:,}")

    # Collect (doc_id, chunk_index, content) triples in batches
    # doc_chunks[doc_id] = list of (chunk_index, content)
    doc_chunks: dict[str, list[tuple[int, str]]] = defaultdict(list)

    batch_size = 5000
    offset = 0
    while offset < total:
        batch = collection.get(
            limit=batch_size,
            offset=offset,
            include=["metadatas", "documents"],
        )
        if not batch["documents"]:
            break
        for meta, text in zip(batch["metadatas"], batch["documents"], strict=True):
            if not meta or not text:
                continue
            doc_id = meta.get("doc_id")
            chunk_index = meta.get("chunk_index")
            if doc_id is None or chunk_index is None:
                continue
            doc_chunks[doc_id].append((int(chunk_index), text))
        offset += len(batch["documents"])
        print(f"  Scanned {offset:,} / {total:,} chunks ...", end="\r")

    print(f"\nFound {len(doc_chunks):,} distinct documents in Chroma.")

    # Sort each document's chunks by chunk_index and check for gaps
    docs_with_gaps: list[str] = []
    for doc_id, pairs in doc_chunks.items():
        pairs.sort(key=lambda p: p[0])
        indices = [p[0] for p in pairs]
        expected = list(range(len(indices)))
        if indices != expected:
            docs_with_gaps.append(doc_id)

    if docs_with_gaps:
        print(f"  Warning: {len(docs_with_gaps)} doc(s) have gaps in chunk_index sequence.")
        for doc_id in docs_with_gaps[:5]:
            indices = [p[0] for p in doc_chunks[doc_id]]
            suffix = "..." if len(indices) > 10 else ""
            print(f"    {doc_id[:16]}...  indices: {indices[:10]}{suffix}")
        if len(docs_with_gaps) > 5:
            print(f"    ... and {len(docs_with_gaps) - 5} more")

    total_chunks = sum(len(pairs) for pairs in doc_chunks.values())
    print(f"Total chunks to write: {total_chunks:,}")

    if args.dry_run:
        print("\nDry run — no data written.")
        return

    from rkb.core.chunk_store import ChunkStore

    store = ChunkStore(chunks_db_path)
    docs_written = 0
    for doc_id, pairs in doc_chunks.items():
        store.upsert_chunks(doc_id, pairs)
        docs_written += 1

    print(f"\nWrote {docs_written:,} documents ({total_chunks:,} chunks) to {chunks_db_path}.")
    if docs_with_gaps:
        print(f"  {len(docs_with_gaps)} doc(s) had non-contiguous chunk_index — stored as-is.")


if __name__ == "__main__":
    main()
