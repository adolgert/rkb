"""One-time reconciliation of scattered PDF collections."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

from rkb.collection.canonical_store import canonical_dir, is_stored, store_pdf
from rkb.collection.catalog import Catalog
from rkb.collection.display_name import generate_display_name
from rkb.collection.hashing import hash_file_sha256
from rkb.collection.ingest import _build_zotero_client, _get_page_count
from rkb.collection.scanner import scan_pdf_files
from rkb.collection.zotero_sync import scan_zotero_hashes, sync_batch_to_zotero

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from pathlib import Path

    from rkb.collection.config import CollectionConfig

_PROGRESS_THRESHOLD = 10


@dataclass
class RectifyFailure:
    """Rectify action failure details."""

    path: str
    error: str


@dataclass
class RectifySummary:
    """Aggregate metrics for rectify command reporting."""

    scanned_directories: int = 0
    total_files_found: int = 0
    unique_pdfs: int = 0
    duplicate_files: int = 0
    canonical_already: int = 0
    canonical_new: int = 0
    zotero_existing: int = 0
    zotero_to_import: int = 0
    zotero_reverse_missing_store: int = 0
    copied_to_canonical: int = 0
    imported_to_zotero: int = 0
    failed: int = 0
    failures: list[RectifyFailure] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert summary to JSON-serializable dictionary."""
        return {
            "scanned_directories": self.scanned_directories,
            "total_files_found": self.total_files_found,
            "unique_pdfs": self.unique_pdfs,
            "duplicate_files": self.duplicate_files,
            "canonical_already": self.canonical_already,
            "canonical_new": self.canonical_new,
            "zotero_existing": self.zotero_existing,
            "zotero_to_import": self.zotero_to_import,
            "zotero_reverse_missing_store": self.zotero_reverse_missing_store,
            "copied_to_canonical": self.copied_to_canonical,
            "imported_to_zotero": self.imported_to_zotero,
            "failed": self.failed,
            "failures": [asdict(failure) for failure in self.failures],
        }

    def exit_code(self) -> int:
        """Return rectify command exit code."""
        return 2 if self.failed > 0 else 0


def _catalog_is_known(catalog: Catalog, content_sha256: str) -> bool:
    try:
        return catalog.is_known(content_sha256)
    except sqlite3.OperationalError:
        return False


def _canonical_file_path(library_root: Path, content_sha256: str) -> Path | None:
    directory = canonical_dir(library_root, content_sha256)
    if not directory.exists():
        return None
    pdfs = sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() == ".pdf"
    )
    if not pdfs:
        return None
    return pdfs[0]


def _ensure_catalog_entry(
    *,
    catalog: Catalog,
    content_sha256: str,
    canonical_path: Path,
    source_path: Path,
) -> None:
    if not _catalog_is_known(catalog, content_sha256):
        page_count = _get_page_count(canonical_path)
        catalog.add_canonical_file(
            content_sha256=content_sha256,
            canonical_path=str(canonical_path),
            display_name=canonical_path.name,
            original_filename=source_path.name,
            page_count=page_count,
            file_size_bytes=canonical_path.stat().st_size,
        )


def _record_failure(summary: RectifySummary, path: Path | str, error: Exception | str) -> None:
    summary.failed += 1
    summary.failures.append(RectifyFailure(path=str(path), error=str(error)))


def _compute_catalog_hashes(catalog: Catalog) -> set[str]:
    try:
        return set(catalog.list_canonical_hashes())
    except sqlite3.OperationalError:
        return set()


def _append_zotero_failures_for_hashes(
    *,
    summary: RectifySummary,
    catalog: Catalog,
    content_hashes: Iterable[str],
) -> None:
    for content_hash in content_hashes:
        link = catalog.get_zotero_link(content_hash)
        if not link or link["status"] != "failed":
            continue

        row = catalog.get_canonical_file(content_hash)
        canonical_path = row["canonical_path"] if row else content_hash
        message = link["error_message"] or "zotero import failed"
        _record_failure(summary, canonical_path, f"zotero: {message}")


def _record_global_zotero_failure(
    *,
    summary: RectifySummary,
    catalog: Catalog,
    content_hashes: Iterable[str],
    error: Exception,
) -> None:
    message = f"zotero setup error: {error}"
    for content_hash in content_hashes:
        catalog.set_zotero_link(content_hash, None, "failed", error_message=str(error))
        catalog.log_action(content_hash, "failed", detail=message)
        row = catalog.get_canonical_file(content_hash)
        canonical_path = row["canonical_path"] if row else content_hash
        _record_failure(summary, canonical_path, message)


def _iter_paths_with_progress(paths: list[Path], description: str):
    if len(paths) <= _PROGRESS_THRESHOLD:
        return paths

    try:
        from tqdm import tqdm
    except ImportError:
        return paths

    return tqdm(paths, desc=description, unit="file")


def _iter_hashes_with_progress(hashes: list[str], description: str):
    if len(hashes) <= _PROGRESS_THRESHOLD:
        return hashes

    try:
        from tqdm import tqdm
    except ImportError:
        return hashes

    return tqdm(hashes, desc=description, unit="file")


def _build_zotero_progress_callback(
    total: int,
) -> tuple[Callable[[dict], None] | None, Callable[[], None]]:
    if total <= _PROGRESS_THRESHOLD:
        return None, lambda: None

    try:
        from tqdm import tqdm
    except ImportError:
        return None, lambda: None

    progress = tqdm(total=total, desc="Rectify Zotero sync", unit="file")

    def callback(_event: dict) -> None:
        progress.update(1)

    def close() -> None:
        progress.close()

    return callback, close


def _validate_non_empty_pdf(path: Path) -> None:
    if path.stat().st_size == 0:
        raise ValueError(f"Zero-byte PDF: {path}")


def rectify_collection(  # noqa: PLR0912
    *,
    scan_directories: list[Path],
    config: CollectionConfig,
    dry_run: bool = False,
    report: bool = False,
    skip_zotero: bool = False,
) -> RectifySummary:
    """Reconcile scattered PDFs into canonical store and Zotero coverage."""
    discovered_paths = scan_pdf_files(scan_directories)
    summary = RectifySummary(
        scanned_directories=len(scan_directories),
        total_files_found=len(discovered_paths),
    )

    discovered_by_hash: dict[str, list[Path]] = {}
    for path in _iter_paths_with_progress(discovered_paths, "Rectify hash scan"):
        try:
            _validate_non_empty_pdf(path)
            content_sha256 = hash_file_sha256(path)
            discovered_by_hash.setdefault(content_sha256, []).append(path)
        except Exception as error:
            _record_failure(summary, path, error)

    summary.unique_pdfs = len(discovered_by_hash)
    duplicate_count = sum(len(paths) for paths in discovered_by_hash.values())
    summary.duplicate_files = max(0, duplicate_count - summary.unique_pdfs)

    write_catalog = Catalog(config.catalog_db)
    read_catalog: Catalog | None = write_catalog

    if report or dry_run:
        read_catalog = Catalog(config.catalog_db) if config.catalog_db.exists() else None
    else:
        (config.library_root / "sha256").mkdir(parents=True, exist_ok=True)
        write_catalog.initialize()

    try:
        catalog_hashes = (
            _compute_catalog_hashes(read_catalog)
            if read_catalog is not None
            else set()
        )

        missing_from_store: dict[str, Path] = {}
        for content_sha256, sources in discovered_by_hash.items():
            if is_stored(config.library_root, content_sha256):
                summary.canonical_already += 1
            else:
                summary.canonical_new += 1
                missing_from_store[content_sha256] = sources[0]

        zotero_hashes: dict[str, Path] = {}
        if config.zotero_storage.exists():
            try:
                zotero_hashes = scan_zotero_hashes(config.zotero_storage)
            except Exception as error:
                _record_failure(summary, config.zotero_storage, error)

        reverse_missing: dict[str, Path] = {}
        for content_sha256, zotero_path in zotero_hashes.items():
            if is_stored(config.library_root, content_sha256):
                continue
            if content_sha256 in missing_from_store:
                continue
            reverse_missing[content_sha256] = zotero_path

        summary.zotero_reverse_missing_store = len(reverse_missing)

        if not report and not dry_run:
            copy_plan = dict(missing_from_store)
            for content_sha256, source_path in reverse_missing.items():
                copy_plan.setdefault(content_sha256, source_path)

            # Forward gap (scanned sources -> canonical store)
            copy_hashes = sorted(copy_plan)
            for content_sha256 in _iter_hashes_with_progress(
                copy_hashes, "Rectify canonical copy"
            ):
                source_path = copy_plan[content_sha256]
                try:
                    stored_path = store_pdf(
                        config.library_root,
                        source_path,
                        content_sha256,
                        generate_display_name(source_path),
                    )
                    _ensure_catalog_entry(
                        catalog=write_catalog,
                        content_sha256=content_sha256,
                        canonical_path=stored_path,
                        source_path=source_path,
                    )
                    write_catalog.add_source_sighting(
                        content_sha256,
                        str(source_path),
                        config.machine_id,
                    )
                    summary.copied_to_canonical += 1
                except Exception as error:
                    _record_failure(summary, source_path, error)

            # Ensure discovered files are fully represented in catalog and provenance.
            for content_sha256, sources in discovered_by_hash.items():
                canonical_path = _canonical_file_path(config.library_root, content_sha256)
                if canonical_path is None:
                    continue
                try:
                    _ensure_catalog_entry(
                        catalog=write_catalog,
                        content_sha256=content_sha256,
                        canonical_path=canonical_path,
                        source_path=sources[0],
                    )
                    for source in sources:
                        write_catalog.add_source_sighting(
                            content_sha256,
                            str(source),
                            config.machine_id,
                        )
                except Exception as error:
                    _record_failure(summary, sources[0], error)

            # Ensure reverse-gap Zotero files keep provenance even if not explicitly scanned.
            for content_sha256, zotero_path in reverse_missing.items():
                canonical_path = _canonical_file_path(config.library_root, content_sha256)
                if canonical_path is None:
                    continue
                try:
                    _ensure_catalog_entry(
                        catalog=write_catalog,
                        content_sha256=content_sha256,
                        canonical_path=canonical_path,
                        source_path=zotero_path,
                    )
                    write_catalog.add_source_sighting(
                        content_sha256,
                        str(zotero_path),
                        config.machine_id,
                    )
                except Exception as error:
                    _record_failure(summary, zotero_path, error)

            catalog_hashes = _compute_catalog_hashes(write_catalog)
        else:
            catalog_hashes = catalog_hashes.union(discovered_by_hash.keys())
            catalog_hashes = catalog_hashes.union(reverse_missing.keys())

        if not skip_zotero:
            target_hashes = sorted(catalog_hashes)
            to_import = [
                content_hash
                for content_hash in target_hashes
                if content_hash not in zotero_hashes
            ]
            summary.zotero_existing = len(target_hashes) - len(to_import)
            summary.zotero_to_import = len(to_import)

            if not report and not dry_run and to_import:
                try:
                    zot_client = _build_zotero_client(config)
                    progress_callback, close_progress = _build_zotero_progress_callback(
                        len(to_import)
                    )
                    try:
                        zot_summary = sync_batch_to_zotero(
                            hashes_to_import=to_import,
                            catalog=write_catalog,
                            library_root=config.library_root,
                            zot=zot_client,
                            zotero_hashes=zotero_hashes,
                            progress_callback=progress_callback,
                        )
                    finally:
                        close_progress()
                    summary.imported_to_zotero += zot_summary["imported"]
                    _append_zotero_failures_for_hashes(
                        summary=summary,
                        catalog=write_catalog,
                        content_hashes=to_import,
                    )
                except Exception as error:
                    _record_global_zotero_failure(
                        summary=summary,
                        catalog=write_catalog,
                        content_hashes=to_import,
                        error=error,
                    )

    finally:
        if read_catalog is not None and read_catalog is not write_catalog:
            read_catalog.close()
        write_catalog.close()

    return summary
