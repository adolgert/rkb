"""Topics command - Discover latent topics across the corpus using BERTopic."""
# ruff: noqa: T201

from __future__ import annotations

import csv
import logging
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import argparse

LOGGER = logging.getLogger("rkb.cli.commands.topics_cmd")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add command-specific arguments."""
    parser.add_argument(
        "--nr-topics",
        default="auto",
        help="Number of topics to discover, or 'auto' (default: auto)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="CSV output path (default: topics_YYYYMMDD.csv in cwd)",
    )
    parser.add_argument(
        "--save-model",
        type=Path,
        default=None,
        help="Path to save the fitted BERTopic model for later use",
    )
    parser.add_argument(
        "--min-cluster-size",
        type=int,
        default=10,
        help="Minimum cluster size for HDBSCAN (default: 10); lower gives more topics",
    )
    parser.add_argument(
        "--vector-db-path",
        type=Path,
        default=None,
        help="Path to Chroma vector database (default: <library>/sha256/rkb_chroma_db)",
    )
    parser.add_argument(
        "--chunks-db-path",
        type=Path,
        default=None,
        help="Path to rkb_chunks.db (default: <library>/sha256/rkb_chunks.db)",
    )
    parser.add_argument(
        "--catalog-db-path",
        type=Path,
        default=None,
        help="Path to pdf_catalog.db (default: from config)",
    )
    parser.add_argument(
        "--collection-name",
        default="documents",
        help="Chroma collection name (default: documents)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5000,
        help="Batch size for fetching embeddings from Chroma (default: 5000)",
    )


def _fetch_all_embeddings(
    chroma_path: Path,
    collection_name: str,
    batch_size: int,
) -> tuple[list[str], np.ndarray, dict[str, list[str]]]:
    """Fetch all chunk embeddings from Chroma and mean-pool per doc_id.

    Args:
        chroma_path: Path to the Chroma database directory.
        collection_name: Name of the Chroma collection.
        batch_size: Number of chunks to fetch per request.

    Returns:
        Tuple of:
        - doc_ids: list of unique doc_ids in stable order
        - embeddings: float32 array of shape (n_docs, 768) — mean-pooled
        - doc_chunk_ids: mapping from doc_id to list of chunk IDs (for debugging)
    """
    import chromadb

    LOGGER.info("Connecting to Chroma at %s", chroma_path)
    client = chromadb.PersistentClient(path=str(chroma_path))
    collection = client.get_collection(collection_name)

    total = collection.count()
    LOGGER.info("Collection contains %d chunks", total)
    print(f"Fetching {total:,} chunk embeddings from Chroma ...")

    # Accumulate embeddings per doc_id
    doc_embeddings: dict[str, list[list[float]]] = defaultdict(list)
    doc_chunk_ids: dict[str, list[str]] = defaultdict(list)

    offset = 0
    fetched = 0
    while offset < total:
        batch = collection.get(
            limit=batch_size,
            offset=offset,
            include=["embeddings", "metadatas"],
        )
        if not batch or not batch["ids"]:
            break

        ids = batch["ids"]
        embeddings = batch["embeddings"]
        metadatas = batch["metadatas"] or [{}] * len(ids)

        for chunk_id, emb, meta in zip(ids, embeddings, metadatas, strict=False):
            doc_id = (meta or {}).get("doc_id")
            if doc_id and emb is not None:
                doc_embeddings[doc_id].append(emb)
                doc_chunk_ids[doc_id].append(chunk_id)

        fetched += len(ids)
        offset += batch_size
        print(f"  {fetched:,} / {total:,} chunks fetched ...", end="\r", flush=True)

    print()  # newline after progress

    LOGGER.info("Found %d unique documents", len(doc_embeddings))

    # Mean-pool
    doc_ids = sorted(doc_embeddings.keys())
    pooled = np.array(
        [np.mean(doc_embeddings[did], axis=0) for did in doc_ids],
        dtype=np.float32,
    )
    LOGGER.info("Mean-pooled embeddings shape: %s", pooled.shape)
    return doc_ids, pooled, dict(doc_chunk_ids)


def _fetch_doc_texts(chunks_db_path: Path, doc_ids: list[str]) -> dict[str, str]:
    """Concatenate all chunk text per document from rkb_chunks.db.

    Args:
        chunks_db_path: Path to SQLite chunks database.
        doc_ids: List of doc_ids to retrieve text for.

    Returns:
        Mapping from doc_id to concatenated text (empty string if not found).
    """
    if not chunks_db_path.exists():
        LOGGER.warning("Chunks DB not found at %s; using empty documents", chunks_db_path)
        return dict.fromkeys(doc_ids, "")

    LOGGER.info("Loading chunk text from %s", chunks_db_path)
    doc_texts: dict[str, list[str]] = defaultdict(list)
    target_set = set(doc_ids)

    with sqlite3.connect(str(chunks_db_path)) as conn:
        cursor = conn.execute(
            "SELECT doc_id, chunk_idx, content FROM chunks ORDER BY doc_id, chunk_idx"
        )
        for doc_id, _idx, content in cursor:
            if doc_id in target_set:
                doc_texts[doc_id].append(content)

    return {did: " ".join(doc_texts.get(did, [""])) for did in doc_ids}


def _fetch_doc_metadata(catalog_db_path: Path, doc_ids: list[str]) -> dict[str, dict]:
    """Retrieve title and year per document from pdf_catalog.db.

    Args:
        catalog_db_path: Path to the catalog database.
        doc_ids: List of doc_ids to look up.

    Returns:
        Mapping from doc_id to dict with keys 'title' and 'year'.
    """
    result: dict[str, dict] = {did: {"title": did, "year": ""} for did in doc_ids}
    if not catalog_db_path.exists():
        LOGGER.warning("Catalog DB not found at %s; titles will be doc_ids", catalog_db_path)
        return result

    try:
        with sqlite3.connect(str(catalog_db_path)) as conn:
            # Try common column names; gracefully degrade if schema differs
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("PRAGMA table_info(documents)")
            columns = {row["name"] for row in cursor.fetchall()}

            title_col = next(
                (c for c in ("title", "name", "filename") if c in columns), None
            )
            year_col = next(
                (c for c in ("year", "publication_year", "date") if c in columns), None
            )
            id_col = next(
                (c for c in ("sha256", "doc_id", "id") if c in columns), None
            )

            if id_col is None:
                LOGGER.warning("Cannot find doc_id column in catalog; using fallback titles")
                return result

            select_cols = id_col
            if title_col:
                select_cols += f", {title_col}"
            if year_col:
                select_cols += f", {year_col}"

            cursor = conn.execute(f"SELECT {select_cols} FROM documents")  # noqa: S608
            for row in cursor.fetchall():
                doc_id = row[id_col]
                if doc_id in result:
                    result[doc_id]["title"] = row[title_col] if title_col else doc_id
                    result[doc_id]["year"] = str(row[year_col]) if year_col else ""
    except Exception:
        LOGGER.exception("Error reading catalog DB; continuing with doc_id as title")

    return result


def _run_bertopic(
    docs: list[str],
    embeddings: np.ndarray,
    nr_topics: str | int,
    min_cluster_size: int,
) -> tuple[list[int], object]:
    """Fit BERTopic on pre-computed embeddings.

    Args:
        docs: One text string per document (for c-TF-IDF keyword extraction).
        embeddings: Float32 array of shape (n_docs, dim).
        nr_topics: Target topic count or "auto".
        min_cluster_size: HDBSCAN minimum cluster size.

    Returns:
        Tuple of (topic_assignments, fitted_topic_model).
    """
    try:
        from bertopic import BERTopic
        from hdbscan import HDBSCAN
        from sklearn.feature_extraction.text import CountVectorizer
        from umap import UMAP
    except ImportError as exc:
        msg = (
            "BERTopic dependencies are not installed. "
            "Run: uv sync --extra topics"
        )
        raise ImportError(msg) from exc

    umap_model = UMAP(
        n_components=5,
        n_neighbors=15,
        min_dist=0.0,
        metric="cosine",
        random_state=42,
    )
    hdbscan_model = HDBSCAN(
        min_cluster_size=min_cluster_size,
        metric="euclidean",
        cluster_selection_method="eom",
        prediction_data=True,
    )

    nr_topics_arg: str | int | None = None
    if nr_topics != "auto":
        try:
            nr_topics_arg = int(nr_topics)
        except ValueError:
            LOGGER.warning("Invalid --nr-topics value '%s'; using auto", nr_topics)

    vectorizer_model = CountVectorizer(
        stop_words="english",
        min_df=2,
        ngram_range=(1, 2),
    )

    topic_model = BERTopic(
        umap_model=umap_model,
        hdbscan_model=hdbscan_model,
        vectorizer_model=vectorizer_model,
        embedding_model=None,
        calculate_probabilities=False,
        nr_topics=nr_topics_arg,
        verbose=True,
    )

    print(f"Running BERTopic on {len(docs)} documents ...")
    topics, _ = topic_model.fit_transform(docs, embeddings)
    return topics, topic_model


def _print_topic_summary(topic_model: object, topics: list[int]) -> None:  # noqa: T201
    """Print a human-readable topic summary to stdout."""
    topic_counts: dict[int, int] = defaultdict(int)
    for t in topics:
        topic_counts[t] += 1

    n_topics = len(topic_counts) - (1 if -1 in topic_counts else 0)
    n_outliers = topic_counts.get(-1, 0)
    print(f"\nDiscovered {n_topics} topics ({n_outliers} documents unassigned)")
    print("=" * 60)

    topic_info = topic_model.get_topic_info()  # type: ignore[attr-defined]
    # Show top-10 non-outlier topics sorted by document count
    shown = 0
    for _, row in topic_info.iterrows():
        tid = row["Topic"]
        if tid == -1:
            continue
        count = topic_counts.get(tid, 0)
        # BERTopic stores top words in "Name" or we can call get_topic()
        words = topic_model.get_topic(tid)  # type: ignore[attr-defined]
        label = ", ".join(w for w, _ in words[:5]) if words else str(row.get("Name", tid))
        print(f"  Topic {tid:3d} ({count:4d} docs): {label}")
        shown += 1
        if shown >= 10:
            break
    print()


def _write_csv(
    output_path: Path,
    doc_ids: list[str],
    topics: list[int],
    topic_model: object,
    doc_metadata: dict[str, dict],
) -> None:
    """Write per-document topic assignments to a CSV file."""
    # Build topic label lookup
    topic_labels: dict[int, str] = {}
    for tid in set(topics):
        words = topic_model.get_topic(tid)  # type: ignore[attr-defined]
        if words:
            topic_labels[tid] = "_".join(w for w, _ in words[:3])
        else:
            topic_labels[tid] = f"topic_{tid}" if tid >= 0 else "outlier"

    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["doc_id", "title", "year", "topic_id", "topic_label"])
        for doc_id, topic_id in zip(doc_ids, topics, strict=True):
            meta = doc_metadata.get(doc_id, {"title": doc_id, "year": ""})
            writer.writerow([
                doc_id,
                meta.get("title", doc_id),
                meta.get("year", ""),
                topic_id,
                topic_labels.get(topic_id, ""),
            ])

    print(f"Wrote {len(doc_ids)} rows to {output_path}")


def execute(args: argparse.Namespace) -> int:
    """Execute the topics command."""
    from rkb.collection.config import CollectionConfig

    config = CollectionConfig.load(getattr(args, "config", None))
    sha256_dir = config.library_root / "sha256"

    if args.vector_db_path is None:
        args.vector_db_path = sha256_dir / "rkb_chroma_db"
    if args.chunks_db_path is None:
        args.chunks_db_path = sha256_dir / "rkb_chunks.db"
    if args.catalog_db_path is None:
        args.catalog_db_path = config.catalog_db

    if not args.vector_db_path.exists():
        print(f"Vector database not found at {args.vector_db_path}")
        print("Run 'rkb index' first.")
        return 1

    if args.output is None:
        date_str = datetime.now().strftime("%Y%m%d")  # noqa: DTZ005
        args.output = Path(f"topics_{date_str}.csv")

    nr_topics: str | int = args.nr_topics
    if nr_topics != "auto":
        try:
            nr_topics = int(nr_topics)
        except ValueError:
            print(f"Invalid --nr-topics value '{nr_topics}'. Use an integer or 'auto'.")
            return 1

    try:
        # Step 1: fetch embeddings from Chroma and mean-pool per document
        doc_ids, embeddings, _ = _fetch_all_embeddings(
            chroma_path=args.vector_db_path,
            collection_name=args.collection_name,
            batch_size=args.batch_size,
        )

        if len(doc_ids) == 0:
            print("No documents found in the vector database.")
            return 1

        print(f"Mean-pooled embeddings for {len(doc_ids):,} documents.")

        # Step 2: load document text for c-TF-IDF
        docs = list(_fetch_doc_texts(args.chunks_db_path, doc_ids).values())

        # Step 3: run BERTopic
        topics, topic_model = _run_bertopic(
            docs=docs,
            embeddings=embeddings,
            nr_topics=nr_topics,
            min_cluster_size=args.min_cluster_size,
        )

        # Step 4: load metadata for CSV output
        doc_metadata = _fetch_doc_metadata(args.catalog_db_path, doc_ids)

        # Step 5: print summary
        _print_topic_summary(topic_model, topics)

        # Step 6: write CSV
        _write_csv(
            output_path=args.output,
            doc_ids=doc_ids,
            topics=topics,
            topic_model=topic_model,
            doc_metadata=doc_metadata,
        )

        # Step 7: optionally save the model
        if args.save_model is not None:
            topic_model.save(str(args.save_model))  # type: ignore[attr-defined]
            print(f"Saved BERTopic model to {args.save_model}")

        return 0

    except ImportError as exc:
        print(f"Missing dependency: {exc}")
        return 1
    except Exception as exc:
        LOGGER.exception("Unexpected error in topics command")
        if getattr(args, "verbose", False):
            import traceback
            traceback.print_exc()
        else:
            print(f"Error: {exc}")
        return 1
