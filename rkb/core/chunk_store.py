"""Persistent chunk text store backed by SQLite."""

import sqlite3
from pathlib import Path


class ChunkStore:
    """SQLite store for chunk text, keyed by (doc_id, chunk_idx)."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self._init_database()

    def _init_database(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    doc_id    TEXT    NOT NULL,
                    chunk_idx INTEGER NOT NULL,
                    content   TEXT    NOT NULL,
                    PRIMARY KEY (doc_id, chunk_idx)
                )
            """)

    def upsert_chunks(self, doc_id: str, chunks: list[tuple[int, str]]) -> None:
        """Insert or replace chunks for a document.

        Args:
            doc_id: Document identifier (sha256).
            chunks: List of (chunk_idx, content) pairs.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO chunks (doc_id, chunk_idx, content) VALUES (?, ?, ?)",
                [(doc_id, idx, text) for idx, text in chunks],
            )

    def get_chunks(self, doc_id: str, start: int, finish: int) -> list[tuple[int, str]]:
        """Return chunks for doc_id with chunk_idx in [start, finish].

        Args:
            doc_id: Document identifier.
            start: Inclusive lower bound on chunk_idx.
            finish: Inclusive upper bound on chunk_idx.

        Returns:
            List of (chunk_idx, content) ordered by chunk_idx.
        """
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT chunk_idx, content FROM chunks
                WHERE doc_id = ? AND chunk_idx BETWEEN ? AND ?
                ORDER BY chunk_idx
                """,
                (doc_id, start, finish),
            ).fetchall()
        return [(row[0], row[1]) for row in rows]

    def delete_doc(self, doc_id: str) -> int:
        """Delete all chunks for a document.

        Returns:
            Number of rows deleted.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM chunks WHERE doc_id = ?",
                (doc_id,),
            )
            return cursor.rowcount

    def get_chunk_count(self, doc_id: str) -> int:
        """Return the number of chunks stored for a document."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE doc_id = ?",
                (doc_id,),
            ).fetchone()
        return row[0] if row else 0
