"""SQLite catalog for canonical PDF collection state."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class Catalog:
    """Database wrapper for `pdf_catalog.db` operations."""

    db_path: Path | str
    _connection: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._connection is None:
            db_target = ":memory:" if str(self.db_path) == ":memory:" else str(self.db_path)
            self._connection = sqlite3.connect(db_target)
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def close(self) -> None:
        """Close underlying database connection, if open."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def initialize(self) -> None:
        """Create catalog tables if they do not already exist."""
        if str(self.db_path) != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        connection = self._connect()
        connection.executescript(
            """
                CREATE TABLE IF NOT EXISTS canonical_files (
                    content_sha256 TEXT PRIMARY KEY,
                    canonical_path TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    original_filename TEXT,
                    page_count INTEGER,
                    file_size_bytes INTEGER,
                    ingested_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS source_sightings (
                    content_sha256 TEXT NOT NULL
                        REFERENCES canonical_files(content_sha256),
                    source_path TEXT NOT NULL,
                    machine_id TEXT NOT NULL,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    PRIMARY KEY (content_sha256, source_path, machine_id)
                );

                CREATE INDEX IF NOT EXISTS idx_sightings_hash
                    ON source_sightings(content_sha256);

                CREATE TABLE IF NOT EXISTS zotero_links (
                    content_sha256 TEXT PRIMARY KEY
                        REFERENCES canonical_files(content_sha256),
                    zotero_item_key TEXT,
                    zotero_attachment_key TEXT,
                    status TEXT NOT NULL
                        CHECK(status IN ('imported', 'pre-existing', 'failed', 'pending')),
                    error_message TEXT,
                    linked_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ingest_log (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_sha256 TEXT NOT NULL,
                    action TEXT NOT NULL,
                    source_path TEXT,
                    detail TEXT,
                    timestamp TEXT NOT NULL
                );
            """
        )
        connection.commit()

    def add_canonical_file(
        self,
        content_sha256: str,
        canonical_path: str,
        display_name: str,
        original_filename: str | None,
        page_count: int | None,
        file_size_bytes: int | None,
    ) -> None:
        """Insert one canonical file row."""
        connection = self._connect()
        connection.execute(
            """
                INSERT INTO canonical_files (
                    content_sha256, canonical_path, display_name, original_filename,
                    page_count, file_size_bytes, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
            (
                content_sha256,
                canonical_path,
                display_name,
                original_filename,
                page_count,
                file_size_bytes,
                _utc_now_iso(),
            ),
        )
        connection.commit()

    def is_known(self, content_sha256: str) -> bool:
        """Return True if hash exists in canonical_files."""
        connection = self._connect()
        row = connection.execute(
            "SELECT 1 FROM canonical_files WHERE content_sha256 = ?",
            (content_sha256,),
        ).fetchone()
        return row is not None

    def get_canonical_file(self, content_sha256: str) -> dict | None:
        """Return canonical file row as dict, if present."""
        connection = self._connect()
        row = connection.execute(
            "SELECT * FROM canonical_files WHERE content_sha256 = ?",
            (content_sha256,),
        ).fetchone()
        return dict(row) if row else None

    def add_source_sighting(
        self,
        content_sha256: str,
        source_path: str,
        machine_id: str,
    ) -> None:
        """Insert or update a source sighting row."""
        now = _utc_now_iso()
        connection = self._connect()
        connection.execute(
            """
                INSERT INTO source_sightings (
                    content_sha256, source_path, machine_id, first_seen, last_seen
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(content_sha256, source_path, machine_id)
                DO UPDATE SET last_seen = excluded.last_seen
                """,
            (content_sha256, source_path, machine_id, now, now),
        )
        connection.commit()

    def set_zotero_link(
        self,
        content_sha256: str,
        zotero_item_key: str | None,
        status: str,
        zotero_attachment_key: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Insert or update Zotero linkage status."""
        connection = self._connect()
        connection.execute(
            """
                INSERT INTO zotero_links (
                    content_sha256, zotero_item_key, zotero_attachment_key,
                    status, error_message, linked_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(content_sha256)
                DO UPDATE SET
                    zotero_item_key = excluded.zotero_item_key,
                    zotero_attachment_key = excluded.zotero_attachment_key,
                    status = excluded.status,
                    error_message = excluded.error_message,
                    linked_at = excluded.linked_at
                """,
            (
                content_sha256,
                zotero_item_key,
                zotero_attachment_key,
                status,
                error_message,
                _utc_now_iso(),
            ),
        )
        connection.commit()

    def get_unlinked_to_zotero(self) -> list[str]:
        """Return hashes missing Zotero links or marked as failed."""
        connection = self._connect()
        rows = connection.execute(
            """
                SELECT c.content_sha256
                FROM canonical_files AS c
                LEFT JOIN zotero_links AS z
                    ON z.content_sha256 = c.content_sha256
                WHERE z.content_sha256 IS NULL
                   OR z.status IN ('failed', 'pending')
                ORDER BY c.content_sha256
            """
        ).fetchall()
        return [row["content_sha256"] for row in rows]

    def get_zotero_link(self, content_sha256: str) -> dict | None:
        """Return one zotero_links row by content hash, if present."""
        row = self._connect().execute(
            "SELECT * FROM zotero_links WHERE content_sha256 = ?",
            (content_sha256,),
        ).fetchone()
        return dict(row) if row else None

    def log_action(
        self,
        content_sha256: str,
        action: str,
        source_path: str | None = None,
        detail: str | None = None,
    ) -> None:
        """Append one ingest log row."""
        connection = self._connect()
        connection.execute(
            """
                INSERT INTO ingest_log (
                    content_sha256, action, source_path, detail, timestamp
                ) VALUES (?, ?, ?, ?, ?)
                """,
            (content_sha256, action, source_path, detail, _utc_now_iso()),
        )
        connection.commit()

    def get_statistics(self) -> dict[str, int]:
        """Return key count metrics for catalog tables."""
        connection = self._connect()
        canonical_count = connection.execute(
            "SELECT COUNT(*) AS count FROM canonical_files"
        ).fetchone()["count"]
        sightings_count = connection.execute(
            "SELECT COUNT(*) AS count FROM source_sightings"
        ).fetchone()["count"]
        links_count = connection.execute(
            "SELECT COUNT(*) AS count FROM zotero_links"
        ).fetchone()["count"]
        log_count = connection.execute(
            "SELECT COUNT(*) AS count FROM ingest_log"
        ).fetchone()["count"]

        return {
            "canonical_files": canonical_count,
            "source_sightings": sightings_count,
            "zotero_links": links_count,
            "ingest_log": log_count,
            "unlinked_to_zotero": len(self.get_unlinked_to_zotero()),
        }

    def list_canonical_hashes(self) -> list[str]:
        """Return all canonical file hashes in ascending order."""
        rows = self._connect().execute(
            "SELECT content_sha256 FROM canonical_files ORDER BY content_sha256"
        ).fetchall()
        return [row["content_sha256"] for row in rows]

    def get_zotero_linked_count(self) -> int:
        """Return number of canonical files successfully linked in Zotero."""
        row = self._connect().execute(
            """
                SELECT COUNT(*) AS count
                FROM canonical_files AS c
                JOIN zotero_links AS z
                    ON z.content_sha256 = c.content_sha256
                WHERE z.status IN ('imported', 'pre-existing')
            """
        ).fetchone()
        return int(row["count"]) if row else 0

    def get_canonical_store_bytes(self) -> int:
        """Return total byte size represented in canonical_files."""
        row = self._connect().execute(
            "SELECT COALESCE(SUM(file_size_bytes), 0) AS total FROM canonical_files"
        ).fetchone()
        return int(row["total"]) if row and row["total"] is not None else 0

    def get_recent_ingest_log(self, *, limit: int = 10) -> list[dict]:
        """Return recent ingest_log rows in reverse chronological order."""
        safe_limit = max(1, int(limit))
        rows = self._connect().execute(
            """
                SELECT log_id, content_sha256, action, source_path, detail, timestamp
                FROM ingest_log
                ORDER BY log_id DESC
                LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
        return [dict(row) for row in rows]
