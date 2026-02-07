"""Ingest orchestration for canonical PDF collection storage."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

from rkb.collection.canonical_store import is_stored, store_pdf
from rkb.collection.catalog import Catalog
from rkb.collection.display_name import generate_display_name
from rkb.collection.hashing import hash_file_sha256
from rkb.collection.scanner import scan_pdf_files

if TYPE_CHECKING:
    from pathlib import Path

    from rkb.collection.config import CollectionConfig


@dataclass
class IngestFailure:
    """Single-file ingest failure details."""

    path: str
    error: str


@dataclass
class IngestSummary:
    """Aggregate ingest results suitable for CLI reporting."""

    scanned: int = 0
    new: int = 0
    duplicate: int = 0
    failed: int = 0
    zotero_imported: int = 0
    zotero_existing: int = 0
    failures: list[IngestFailure] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert ingest summary to JSON-serializable dictionary."""
        return {
            "scanned": self.scanned,
            "new": self.new,
            "duplicate": self.duplicate,
            "failed": self.failed,
            "zotero_imported": self.zotero_imported,
            "zotero_existing": self.zotero_existing,
            "failures": [asdict(failure) for failure in self.failures],
        }

    def exit_code(self) -> int:
        """Return CLI exit code according to ingest status."""
        return 2 if self.failed > 0 else 0


def _get_page_count(pdf_path: Path) -> int | None:
    """Best-effort page count extraction. Failure is non-fatal."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None

    try:
        reader = PdfReader(str(pdf_path))
        return len(reader.pages)
    except Exception:
        return None


def _catalog_is_known(catalog: Catalog, content_sha256: str) -> bool:
    """Check hash presence, tolerating absent tables for dry-run mode."""
    try:
        return catalog.is_known(content_sha256)
    except sqlite3.OperationalError:
        return False


def ingest_directories(
    directories: list[Path],
    config: CollectionConfig,
    *,
    dry_run: bool = False,
    skip_zotero: bool = True,
    no_display_name: bool = False,
) -> IngestSummary:
    """Ingest discovered PDFs into canonical storage and catalog."""
    _ = skip_zotero  # Zotero sync is introduced in a later implementation phase.

    pdf_files = scan_pdf_files(directories)
    summary = IngestSummary(scanned=len(pdf_files))

    write_catalog = Catalog(config.catalog_db)
    lookup_catalog: Catalog | None = write_catalog

    if dry_run:
        lookup_catalog = Catalog(config.catalog_db) if config.catalog_db.exists() else None
    else:
        (config.library_root / "sha256").mkdir(parents=True, exist_ok=True)
        write_catalog.initialize()

    try:
        for pdf_path in pdf_files:
            source_hash: str | None = None
            try:
                source_hash = hash_file_sha256(pdf_path)

                duplicate = is_stored(config.library_root, source_hash)
                if lookup_catalog is not None:
                    duplicate = duplicate or _catalog_is_known(lookup_catalog, source_hash)

                if duplicate:
                    summary.duplicate += 1
                    if not dry_run:
                        write_catalog.add_source_sighting(
                            source_hash,
                            str(pdf_path),
                            config.machine_id,
                        )
                        write_catalog.log_action(
                            source_hash,
                            "skipped_duplicate",
                            source_path=str(pdf_path),
                            detail="already in catalog or canonical store",
                        )
                    continue

                page_count = _get_page_count(pdf_path)
                display_name = (
                    pdf_path.name
                    if no_display_name
                    else generate_display_name(pdf_path)
                )

                if dry_run:
                    summary.new += 1
                    continue

                stored_path = store_pdf(
                    config.library_root,
                    pdf_path,
                    source_hash,
                    display_name,
                )
                write_catalog.add_canonical_file(
                    content_sha256=source_hash,
                    canonical_path=str(stored_path),
                    display_name=stored_path.name,
                    original_filename=pdf_path.name,
                    page_count=page_count,
                    file_size_bytes=pdf_path.stat().st_size,
                )
                write_catalog.add_source_sighting(
                    source_hash,
                    str(pdf_path),
                    config.machine_id,
                )
                write_catalog.log_action(
                    source_hash,
                    "ingested",
                    source_path=str(pdf_path),
                    detail=f"stored at {stored_path}",
                )
                summary.new += 1
            except Exception as error:
                summary.failed += 1
                summary.failures.append(
                    IngestFailure(path=str(pdf_path), error=str(error))
                )
                if not dry_run and source_hash:
                    write_catalog.log_action(
                        source_hash,
                        "failed",
                        source_path=str(pdf_path),
                        detail=str(error),
                    )
    finally:
        if lookup_catalog is not None and lookup_catalog is not write_catalog:
            lookup_catalog.close()
        write_catalog.close()

    return summary
