"""Shared runtime helpers for collection workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from rkb.collection.config import CollectionConfig


def get_page_count(pdf_path: Path) -> int | None:
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


def build_zotero_client(config: CollectionConfig) -> object:
    """Create a pyzotero client from collection configuration."""
    if not config.zotero_library_id:
        raise RuntimeError("Missing Zotero credential: ZOTERO_LIBRARY_ID")
    if not config.zotero_api_key:
        raise RuntimeError("Missing Zotero credential: ZOTERO_API_KEY")

    try:
        from pyzotero import zotero
    except ImportError as error:
        raise RuntimeError("pyzotero is required. Install the `zotero` extra.") from error

    return zotero.Zotero(
        config.zotero_library_id,
        config.zotero_library_type,
        config.zotero_api_key,
    )
