"""Generate human-readable display names for canonical PDFs."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

_VALID_CHARS = re.compile(r"[^a-zA-Z0-9 ._-]+")
_WHITESPACE = re.compile(r"\s+")
_YEAR = re.compile(r"\b(19|20)\d{2}\b")


def _sanitize_filename(name: str) -> str:
    cleaned = _VALID_CHARS.sub(" ", name)
    cleaned = _WHITESPACE.sub(" ", cleaned).strip()
    if not cleaned:
        cleaned = "document"

    if not cleaned.lower().endswith(".pdf"):
        cleaned = f"{cleaned}.pdf"

    if len(cleaned) <= 120:
        return cleaned

    stem = cleaned[:-4]
    truncated = stem[:116].rstrip(" ._-")
    if not truncated:
        truncated = "document"
    return f"{truncated}.pdf"


def _extract_last_name(author: str) -> str | None:
    normalized = _WHITESPACE.sub(" ", author).strip()
    if not normalized:
        return None

    primary_author = re.split(
        r"\band\b|;|,", normalized, maxsplit=1, flags=re.IGNORECASE
    )[0].strip()
    if not primary_author:
        return None

    parts = primary_author.split()
    return parts[-1] if parts else None


def _extract_first_page_text(pdf_path: Path) -> str | None:
    try:
        from pypdf import PdfReader
    except ImportError:
        return None

    try:
        reader = PdfReader(str(pdf_path))
        if not reader.pages:
            return None
        return reader.pages[0].extract_text()
    except Exception:
        return None


def _name_from_text(text: str) -> str | None:
    lines = [_WHITESPACE.sub(" ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return None

    title_line = lines[0]
    year_match = _YEAR.search(text)
    author_last = None
    if len(lines) > 1:
        author_last = _extract_last_name(lines[1])

    year_text = year_match.group(0) if year_match else None
    parts = [part for part in [author_last, year_text, title_line] if part]
    if not parts:
        return None
    return " ".join(parts)


def generate_display_name(pdf_path: Path, metadata: dict | None = None) -> str:
    """Generate a sanitized display filename with metadata-first priority."""
    if metadata:
        author = metadata.get("author")
        year = metadata.get("year")
        title = metadata.get("title")
        author_last = _extract_last_name(str(author)) if author else None
        year_part = str(year) if year else None
        title_part = str(title).strip() if title else None

        parts = [part for part in [author_last, year_part, title_part] if part]
        if parts:
            return _sanitize_filename(" ".join(parts))

    first_page_text = _extract_first_page_text(pdf_path)
    if first_page_text:
        text_name = _name_from_text(first_page_text)
        if text_name:
            return _sanitize_filename(text_name)

    fallback = pdf_path.name or pdf_path.stem or "document.pdf"
    return _sanitize_filename(fallback)
