"""Ingest orchestration for canonical PDF collection storage."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

from rkb.collection.canonical_store import is_stored, store_pdf
from rkb.collection.catalog import Catalog
from rkb.collection.display_name import generate_display_name
from rkb.collection.hashing import hash_file_sha256
from rkb.collection.runtime import build_zotero_client, get_page_count
from rkb.collection.scanner import scan_pdf_files
from rkb.collection.zotero_sync import scan_zotero_hashes, sync_batch_to_zotero

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from pathlib import Path

    from rkb.collection.config import CollectionConfig

_PROGRESS_THRESHOLD = 10


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


def _catalog_is_known(catalog: Catalog, content_sha256: str) -> bool:
    """Check hash presence, tolerating absent tables for dry-run mode."""
    try:
        return catalog.is_known(content_sha256)
    except sqlite3.OperationalError:
        return False


def _record_global_zotero_failure(
    *,
    catalog: Catalog,
    content_hashes: Iterable[str],
    error: Exception,
    summary: IngestSummary,
) -> None:
    """Mark a global Zotero setup failure for each newly ingested hash."""
    message = f"zotero setup error: {error}"
    for content_hash in content_hashes:
        catalog.set_zotero_link(content_hash, None, "failed", error_message=str(error))
        row = catalog.get_canonical_file(content_hash)
        canonical_path = row["canonical_path"] if row else content_hash
        catalog.log_action(content_hash, "failed", detail=message)
        summary.failed += 1
        summary.failures.append(
            IngestFailure(path=str(canonical_path), error=message)
        )


def _append_zotero_failures_for_hashes(
    *,
    catalog: Catalog,
    content_hashes: Iterable[str],
    summary: IngestSummary,
) -> None:
    """Append per-file Zotero failure details to ingest summary."""
    for content_hash in content_hashes:
        link_row = catalog.get_zotero_link(content_hash)
        if not link_row or link_row["status"] != "failed":
            continue

        row = catalog.get_canonical_file(content_hash)
        canonical_path = row["canonical_path"] if row else content_hash
        error_message = link_row["error_message"] or "zotero import failed"
        summary.failures.append(
            IngestFailure(path=str(canonical_path), error=f"zotero: {error_message}")
        )


def _iter_with_progress(items: list[Path], description: str):
    if len(items) <= _PROGRESS_THRESHOLD:
        return items

    try:
        from tqdm import tqdm
    except ImportError:
        return items

    return tqdm(items, desc=description, unit="file")


def _build_zotero_progress_callback(
    total: int,
) -> tuple[Callable[[dict], None] | None, Callable[[], None]]:
    if total <= _PROGRESS_THRESHOLD:
        return None, lambda: None

    try:
        from tqdm import tqdm
    except ImportError:
        return None, lambda: None

    progress = tqdm(total=total, desc="Zotero sync", unit="file")

    def callback(_event: dict) -> None:
        progress.update(1)

    def close() -> None:
        progress.close()

    return callback, close


def _validate_non_empty_pdf(path: Path) -> None:
    if path.stat().st_size == 0:
        raise ValueError(f"Zero-byte PDF: {path}")


def ingest_directories(
    directories: list[Path],
    config: CollectionConfig,
    *,
    dry_run: bool = False,
    skip_zotero: bool = True,
    no_display_name: bool = False,
) -> IngestSummary:
    """Ingest discovered PDFs into canonical storage and catalog."""
    pdf_files = scan_pdf_files(directories)
    summary = IngestSummary(scanned=len(pdf_files))
    newly_ingested_hashes: list[str] = []

    write_catalog = Catalog(config.catalog_db)
    lookup_catalog: Catalog | None = write_catalog

    if dry_run:
        lookup_catalog = Catalog(config.catalog_db) if config.catalog_db.exists() else None
    else:
        (config.library_root / "sha256").mkdir(parents=True, exist_ok=True)
        write_catalog.initialize()

    try:
        for pdf_path in _iter_with_progress(pdf_files, "Ingest scan"):
            source_hash: str | None = None
            try:
                _validate_non_empty_pdf(pdf_path)
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

                page_count = get_page_count(pdf_path)
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
                    verify_source=False,
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
                newly_ingested_hashes.append(source_hash)
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

        if (
            not dry_run
            and not skip_zotero
            and newly_ingested_hashes
        ):
            try:
                zotero_hashes = scan_zotero_hashes(config.zotero_storage)
                zot_client = build_zotero_client(config)
                progress_callback, close_progress = _build_zotero_progress_callback(
                    len(newly_ingested_hashes)
                )
                try:
                    zotero_summary = sync_batch_to_zotero(
                        hashes_to_import=newly_ingested_hashes,
                        catalog=write_catalog,
                        library_root=config.library_root,
                        zot=zot_client,
                        zotero_hashes=zotero_hashes,
                        progress_callback=progress_callback,
                    )
                finally:
                    close_progress()
                summary.zotero_imported += zotero_summary["imported"]
                summary.zotero_existing += zotero_summary["skipped"]
                summary.failed += zotero_summary["failed"]
                _append_zotero_failures_for_hashes(
                    catalog=write_catalog,
                    content_hashes=newly_ingested_hashes,
                    summary=summary,
                )
            except Exception as error:
                _record_global_zotero_failure(
                    catalog=write_catalog,
                    content_hashes=newly_ingested_hashes,
                    error=error,
                    summary=summary,
                )
    finally:
        if lookup_catalog is not None and lookup_catalog is not write_catalog:
            lookup_catalog.close()
        write_catalog.close()

    return summary
