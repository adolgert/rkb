"""PDF rendering helpers for the triage web UI."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def get_page_count(pdf_path: Path) -> int | None:
    """Best-effort PDF page count via PyMuPDF."""
    try:
        import fitz
    except ImportError:
        return None

    try:
        with fitz.open(str(pdf_path)) as document:
            return document.page_count
    except Exception:
        return None


def render_pdf_pages_base64(pdf_path: Path, max_pages: int = 2) -> list[str]:
    """Render the first `max_pages` pages as base64-encoded PNG payloads."""
    try:
        import fitz
    except ImportError as error:
        raise RuntimeError("PyMuPDF is required for PDF rendering") from error

    images: list[str] = []
    with fitz.open(str(pdf_path)) as document:
        page_limit = min(max_pages, document.page_count)
        for page_index in range(page_limit):
            pixmap = document[page_index].get_pixmap()
            images.append(base64.b64encode(pixmap.tobytes("png")).decode("ascii"))
    return images
