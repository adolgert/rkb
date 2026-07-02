"""Extract metadata via a local Zotero translation-server.

The translation-server (https://github.com/zotero/translation-server) resolves
identifiers (DOI, arXiv ID, ISBN, PMID) to fully-formed Zotero items using the
same translator code the Zotero client runs. It is self-hosted, so lookups are
not subject to Zotero's metadata-retrieval quota. See docker-compose.yml for
the service definition.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

import pymupdf
import requests

from rkb.extractors.metadata.base import MetadataExtractor
from rkb.extractors.metadata.models import DocumentMetadata

if TYPE_CHECKING:
    from pathlib import Path

DEFAULT_SERVER_URL = "http://localhost:1969"

_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>]+")
_ARXIV_TEXT_RE = re.compile(r"arXiv:\s*(\d{4}\.\d{4,5})", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")

# Zotero itemType -> doc_type, matching the CrossRef-style values already
# stored by the doi_crossref extractor.
_ITEM_TYPE_MAP = {
    "journalArticle": "journal-article",
    "conferencePaper": "proceedings-article",
    "preprint": "preprint",
    "book": "book",
    "bookSection": "book-chapter",
    "report": "report",
    "thesis": "thesis",
}


class ZoteroTranslationExtractor(MetadataExtractor):
    """Resolve DOI/arXiv identifiers to metadata via Zotero translation-server."""

    def __init__(self, server_url: str | None = None, timeout: float = 30.0) -> None:
        self._server_url = (
            server_url
            or os.environ.get("TRANSLATION_SERVER_URL")
            or DEFAULT_SERVER_URL
        ).rstrip("/")
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "zotero_translation"

    def extract(self, pdf_path: Path) -> DocumentMetadata:
        """Find an identifier in the PDF's first pages and resolve it."""
        try:
            identifier = self._find_identifier(pdf_path)
            if identifier is None:
                return DocumentMetadata(extractor=self.name)
            return self.extract_by_identifier(identifier)
        except Exception:
            return DocumentMetadata(extractor=self.name)

    def extract_by_identifier(self, identifier: str) -> DocumentMetadata:
        """Resolve a DOI, arXiv ID, ISBN, or PMID to metadata.

        Returns empty metadata (no title) when the server is unreachable,
        the identifier is unknown, or the response is malformed.
        """
        try:
            response = requests.post(
                f"{self._server_url}/search",
                data=identifier.encode("utf-8"),
                headers={"Content-Type": "text/plain"},
                timeout=self._timeout,
            )
            if response.status_code != 200:
                return DocumentMetadata(extractor=self.name)
            items = response.json()
            if not isinstance(items, list) or not items:
                return DocumentMetadata(extractor=self.name)
            return self._item_to_metadata(items[0])
        except Exception:
            return DocumentMetadata(extractor=self.name)

    def _find_identifier(self, pdf_path: Path) -> str | None:
        """Scan the first pages of a PDF for a DOI or arXiv ID."""
        doc = pymupdf.open(pdf_path)
        try:
            text = ""
            for i in range(min(3, len(doc))):
                text += doc[i].get_text()
        finally:
            doc.close()

        doi_match = _DOI_RE.search(text)
        if doi_match:
            return doi_match.group().rstrip(".,;)")
        arxiv_match = _ARXIV_TEXT_RE.search(text)
        if arxiv_match:
            return f"arXiv:{arxiv_match.group(1)}"
        return None

    def _item_to_metadata(self, item: dict) -> DocumentMetadata:
        """Map a Zotero API item to DocumentMetadata."""
        authors = []
        for creator in item.get("creators", []):
            if creator.get("creatorType") not in (None, "author"):
                continue
            if creator.get("lastName"):
                first = creator.get("firstName", "")
                authors.append(f"{first} {creator['lastName']}".strip())
            elif creator.get("name"):
                authors.append(creator["name"])

        year = None
        year_match = _YEAR_RE.search(item.get("date", "") or "")
        if year_match:
            year = int(year_match.group(1))

        journal = (
            item.get("publicationTitle")
            or item.get("conferenceName")
            or item.get("proceedingsTitle")
            or item.get("repository")
            or None
        )

        return DocumentMetadata(
            doc_type=_ITEM_TYPE_MAP.get(item.get("itemType", ""), item.get("itemType")),
            title=item.get("title") or None,
            authors=authors or None,
            year=year,
            journal=journal,
            abstract=item.get("abstractNote") or None,
            page_count=None,
            extractor=self.name,
        )
