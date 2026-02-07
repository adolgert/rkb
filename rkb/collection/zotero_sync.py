"""Zotero synchronization helpers for canonical collection files."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from rkb.collection.hashing import hash_file_sha256

if TYPE_CHECKING:
    from collections.abc import Callable

    from rkb.collection.catalog import Catalog


def scan_zotero_hashes(zotero_storage: Path) -> dict[str, Path]:
    """Scan Zotero storage and return hash -> one observed PDF path."""
    if not zotero_storage.exists():
        raise FileNotFoundError(zotero_storage)
    if not zotero_storage.is_dir():
        raise NotADirectoryError(zotero_storage)

    hash_map: dict[str, Path] = {}
    for pdf_path in sorted(zotero_storage.rglob("*"), key=str):
        if not pdf_path.is_file():
            continue
        if pdf_path.suffix.lower() != ".pdf":
            continue

        content_sha256 = hash_file_sha256(pdf_path)
        hash_map.setdefault(content_sha256, pdf_path.resolve())

    return hash_map


def is_in_zotero(content_sha256: str, zotero_hashes: dict[str, Path]) -> bool:
    """Return True if the hash appears in the scanned Zotero hash map."""
    return content_sha256 in zotero_hashes


def _extract_item_key(create_items_response: dict) -> str:
    successful = create_items_response.get("successful", {})
    first_success = successful.get("0", {})
    item_key = first_success.get("key")
    if not item_key:
        raise RuntimeError(
            f"Could not parse Zotero item key from response: {create_items_response}"
        )
    return item_key


def _extract_attachment_key(attachment_response: dict) -> str | None:
    successful = attachment_response.get("successful", {})
    first_success = successful.get("0", {})
    return first_success.get("key")


def import_to_zotero(
    canonical_pdf_path: Path,
    display_name: str,
    zot: object,
) -> tuple[str, str | None]:
    """Create a Zotero document item and attach a canonical PDF."""
    template = zot.item_template("document")
    template["title"] = display_name
    created = zot.create_items([template])
    item_key = _extract_item_key(created)
    attachment = zot.attachment_simple([str(canonical_pdf_path)], item_key)
    attachment_key = _extract_attachment_key(attachment)
    return item_key, attachment_key


def _is_rate_limited_error(error: Exception) -> bool:
    message = str(error).lower()
    if "429" in message:
        return True

    status = getattr(error, "status", None)
    if status == 429:
        return True

    response = getattr(error, "response", None)
    return response is not None and getattr(response, "status_code", None) == 429


def _canonical_path_for_hash(catalog: Catalog, content_sha256: str) -> tuple[Path, str]:
    row = catalog.get_canonical_file(content_sha256)
    if row is None:
        raise KeyError(f"Hash not found in catalog: {content_sha256}")

    canonical_path = Path(row["canonical_path"])
    display_name = row.get("display_name", canonical_path.name)
    if not canonical_path.exists():
        raise FileNotFoundError(canonical_path)

    return canonical_path, display_name


def sync_batch_to_zotero(
    hashes_to_import: list[str],
    catalog: Catalog,
    library_root: Path,
    zot: object,
    zotero_hashes: dict[str, Path],
    *,
    max_retries: int = 3,
    base_backoff_seconds: float = 1.0,
    progress_callback: Callable[[dict], None] | None = None,
    sleep_func: Callable[[float], None] = time.sleep,
) -> dict[str, int]:
    """Import missing canonical files into Zotero with 429 retry behavior."""
    _ = library_root

    summary = {"imported": 0, "skipped": 0, "failed": 0}

    for content_sha256 in hashes_to_import:
        if is_in_zotero(content_sha256, zotero_hashes):
            summary["skipped"] += 1
            catalog.set_zotero_link(content_sha256, None, "pre-existing")
            catalog.log_action(
                content_sha256,
                "zotero_skipped",
                detail="already present in Zotero hash scan",
            )
            if progress_callback:
                progress_callback({"hash": content_sha256, "status": "skipped"})
            continue

        try:
            canonical_pdf_path, display_name = _canonical_path_for_hash(catalog, content_sha256)
        except Exception as error:
            summary["failed"] += 1
            catalog.set_zotero_link(
                content_sha256,
                None,
                "failed",
                error_message=str(error),
            )
            catalog.log_action(
                content_sha256,
                "failed",
                detail=f"zotero sync lookup error: {error}",
            )
            if progress_callback:
                progress_callback({"hash": content_sha256, "status": "failed"})
            continue

        retries = 0
        while True:
            try:
                item_key, attachment_key = import_to_zotero(
                    canonical_pdf_path=canonical_pdf_path,
                    display_name=display_name,
                    zot=zot,
                )
                summary["imported"] += 1
                catalog.set_zotero_link(
                    content_sha256,
                    item_key,
                    "imported",
                    zotero_attachment_key=attachment_key,
                )
                catalog.log_action(
                    content_sha256,
                    "zotero_imported",
                    source_path=str(canonical_pdf_path),
                    detail=f"item={item_key}",
                )
                if progress_callback:
                    progress_callback({"hash": content_sha256, "status": "imported"})
                break
            except Exception as error:
                if _is_rate_limited_error(error) and retries < max_retries:
                    retries += 1
                    sleep_func(base_backoff_seconds * (2**(retries - 1)))
                    continue

                summary["failed"] += 1
                catalog.set_zotero_link(
                    content_sha256,
                    None,
                    "failed",
                    error_message=str(error),
                )
                catalog.log_action(
                    content_sha256,
                    "failed",
                    source_path=str(canonical_pdf_path),
                    detail=f"zotero sync error: {error}",
                )
                if progress_callback:
                    progress_callback({"hash": content_sha256, "status": "failed"})
                break

    return summary
