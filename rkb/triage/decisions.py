"""SQLite persistence for triage decisions and decision history."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_ALLOWED_DECISIONS = {"approved", "rejected"}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class TriageDecisionStore:
    """Database wrapper for triage decision state."""

    db_path: Path | str
    _connection: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._connection is None:
            db_target = str(self.db_path)
            self._connection = sqlite3.connect(db_target)
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def close(self) -> None:
        """Close the database connection, if open."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def initialize(self) -> None:
        """Create triage decision tables if they do not already exist."""
        db_file = Path(self.db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        connection = self._connect()
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS triage_decisions (
                content_sha256 TEXT PRIMARY KEY,
                decision TEXT NOT NULL
                    CHECK(decision IN ('approved', 'rejected')),
                original_path TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                file_size_bytes INTEGER,
                page_count INTEGER,
                decided_at TEXT NOT NULL,
                staged_path TEXT
            );

            CREATE TABLE IF NOT EXISTS decision_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_sha256 TEXT NOT NULL,
                old_decision TEXT,
                new_decision TEXT NOT NULL,
                changed_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_triage_decisions_decision
                ON triage_decisions(decision);
            CREATE INDEX IF NOT EXISTS idx_decision_history_hash
                ON decision_history(content_sha256);
            """
        )
        connection.commit()

    def get_decision(self, content_sha256: str) -> dict | None:
        """Return decision row for a hash, if present."""
        row = self._connect().execute(
            "SELECT * FROM triage_decisions WHERE content_sha256 = ?",
            (content_sha256,),
        ).fetchone()
        return dict(row) if row else None

    def get_decisions_map(self, content_hashes: list[str]) -> dict[str, dict]:
        """Return mapping of hash -> decision row for provided hashes."""
        if not content_hashes:
            return {}

        placeholders = ",".join("?" for _ in content_hashes)
        rows = self._connect().execute(
            f"SELECT * FROM triage_decisions WHERE content_sha256 IN ({placeholders})",
            content_hashes,
        ).fetchall()
        return {row["content_sha256"]: dict(row) for row in rows}

    def set_decision(
        self,
        *,
        content_sha256: str,
        decision: str,
        original_path: str,
        original_filename: str,
        file_size_bytes: int | None,
        page_count: int | None,
        staged_path: str | None,
    ) -> dict[str, str | None]:
        """Insert or update current decision and append decision history."""
        if decision not in _ALLOWED_DECISIONS:
            raise ValueError(f"Invalid decision: {decision}")

        connection = self._connect()
        existing = self.get_decision(content_sha256)
        old_decision = existing["decision"] if existing else None
        now = _utc_now_iso()

        connection.execute(
            """
            INSERT INTO triage_decisions (
                content_sha256, decision, original_path, original_filename,
                file_size_bytes, page_count, decided_at, staged_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(content_sha256)
            DO UPDATE SET
                decision = excluded.decision,
                original_path = excluded.original_path,
                original_filename = excluded.original_filename,
                file_size_bytes = excluded.file_size_bytes,
                page_count = excluded.page_count,
                decided_at = excluded.decided_at,
                staged_path = excluded.staged_path
            """,
            (
                content_sha256,
                decision,
                original_path,
                original_filename,
                file_size_bytes,
                page_count,
                now,
                staged_path,
            ),
        )

        if old_decision is None or old_decision != decision:
            connection.execute(
                """
                INSERT INTO decision_history (
                    content_sha256, old_decision, new_decision, changed_at
                ) VALUES (?, ?, ?, ?)
                """,
                (content_sha256, old_decision, decision, now),
            )

        connection.commit()
        return {"old_decision": old_decision, "new_decision": decision}

    def update_staged_path(self, content_sha256: str, staged_path: str | None) -> None:
        """Update staged path for an existing triage decision."""
        self._connect().execute(
            """
            UPDATE triage_decisions
            SET staged_path = ?, decided_at = ?
            WHERE content_sha256 = ?
            """,
            (staged_path, _utc_now_iso(), content_sha256),
        )
        self._connect().commit()

    def list_approved(self) -> list[dict]:
        """Return all currently approved decisions."""
        rows = self._connect().execute(
            """
            SELECT * FROM triage_decisions
            WHERE decision = 'approved'
            ORDER BY decided_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def list_history(self, decision: str | None = None, limit: int = 500) -> list[dict]:
        """Return decision history rows with newest first."""
        connection = self._connect()
        if decision is not None:
            rows = connection.execute(
                """
                SELECT * FROM decision_history
                WHERE new_decision = ?
                ORDER BY changed_at DESC
                LIMIT ?
                """,
                (decision, limit),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT * FROM decision_history
                ORDER BY changed_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_stats(self) -> dict[str, int]:
        """Return summary counts for current triage decisions."""
        connection = self._connect()
        approved = connection.execute(
            "SELECT COUNT(*) AS count FROM triage_decisions WHERE decision = 'approved'"
        ).fetchone()["count"]
        rejected = connection.execute(
            "SELECT COUNT(*) AS count FROM triage_decisions WHERE decision = 'rejected'"
        ).fetchone()["count"]
        total = connection.execute(
            "SELECT COUNT(*) AS count FROM triage_decisions"
        ).fetchone()["count"]
        history = connection.execute(
            "SELECT COUNT(*) AS count FROM decision_history"
        ).fetchone()["count"]
        return {
            "approved": approved,
            "rejected": rejected,
            "total": total,
            "history": history,
        }

