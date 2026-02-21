"""Generate BibTeX entries for canonical PDFs with resolved metadata."""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path


class _HasMetadata(Protocol):
    title: str | None
    authors: list[str] | None
    year: int | None
    abstract: str | None
    journal: str | None
    doc_type: str | None

_ARTICLES = frozenset({"a", "an", "the", "on", "of"})
_ALPHA_NUM = re.compile(r"[^a-z0-9]")

_DOC_TYPE_MAP = {
    "journal-article": "article",
    "proceedings-article": "inproceedings",
    "conference-paper": "inproceedings",
    "book": "book",
    "book-chapter": "inbook",
}


def _strip_accents(text: str) -> str:
    """Remove accents and return ASCII-only lowercase string."""
    nfkd = unicodedata.normalize("NFKD", text)
    return nfkd.encode("ascii", "ignore").decode("ascii").lower()


def _first_last_name(authors: list[str] | None) -> str:
    """Extract lowered ASCII last name of first author, or 'unknown'."""
    if not authors:
        return "unknown"
    first = authors[0].strip()
    if not first:
        return "unknown"
    last = first.split(",")[0].strip() if "," in first else first.split()[-1]
    result = _strip_accents(last)
    return result if result else "unknown"


def _first_title_word(title: str | None) -> str:
    """First substantial word of the title (skip articles), or 'untitled'."""
    if not title:
        return "untitled"
    words = title.lower().split()
    for word in words:
        cleaned = _ALPHA_NUM.sub("", word)
        if cleaned and cleaned not in _ARTICLES:
            return cleaned
    return "untitled"


def generate_citation_key(result: _HasMetadata, content_sha256: str) -> str:
    """Build citation key as author-year-word-hash."""
    author = _first_last_name(result.authors)
    year = str(result.year) if result.year else "nodate"
    word = _first_title_word(result.title)
    hash_part = content_sha256[:12]
    return f"{author}-{year}-{word}-{hash_part}"


def _escape_bibtex(value: str) -> str:
    """Escape special BibTeX characters in a value."""
    return value.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def format_bib_entry(result: _HasMetadata, citation_key: str) -> str:
    """Produce a single BibTeX entry string from resolved metadata."""
    entry_type = _DOC_TYPE_MAP.get(result.doc_type or "", "misc")

    fields: dict[str, str] = {}
    if result.abstract is not None:
        fields["abstract"] = _escape_bibtex(result.abstract)
    if result.authors is not None:
        fields["author"] = " and ".join(result.authors)
    if entry_type == "inproceedings" and result.journal is not None:
        fields["booktitle"] = _escape_bibtex(result.journal)
    elif result.journal is not None:
        fields["journal"] = _escape_bibtex(result.journal)
    if result.title is not None:
        fields["title"] = _escape_bibtex(result.title)
    if result.year is not None:
        fields["year"] = str(result.year)

    lines = [f"@{entry_type}{{{citation_key},"]
    lines.extend(f"  {key} = {{{fields[key]}}}," for key in sorted(fields))
    lines.append("}")
    return "\n".join(lines) + "\n"


def write_bib_file(
    hash_dir: Path, result: _HasMetadata, content_sha256: str
) -> Path:
    """Write metadata.bib into the hash directory. Return the file path."""
    citation_key = generate_citation_key(result, content_sha256)
    entry = format_bib_entry(result, citation_key)
    bib_path = hash_dir / "metadata.bib"
    bib_path.write_text(entry, encoding="utf-8")
    return bib_path
