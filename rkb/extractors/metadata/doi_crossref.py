"""Extract metadata using DOI and CrossRef API."""

import re
from pathlib import Path

import pymupdf
import requests

from rkb.core.text_processing import titles_match
from rkb.extractors.metadata.base import MetadataExtractor
from rkb.extractors.metadata.models import DocumentMetadata

_CROSSREF_TITLE_SOURCE = "crossref_title"
_CROSSREF_SEARCH_URL = "https://api.crossref.org/works"
_CROSSREF_USER_AGENT = "rkb (mailto:claude@dolgert.com)"


class CrossRefUnavailableError(Exception):
    """Raised when CrossRef API is unavailable or rate-limiting."""


class DOICrossRefExtractor(MetadataExtractor):
    """Extract metadata by finding DOI and querying CrossRef API."""

    @property
    def name(self) -> str:
        return "doi_crossref"

    def extract(self, pdf_path: Path) -> DocumentMetadata:
        """Extract metadata using DOI lookup.

        Args:
            pdf_path: Path to PDF file

        Returns:
            DocumentMetadata with fields from CrossRef
        """
        try:
            # Extract text from first few pages to find DOI
            doc = pymupdf.open(pdf_path)
            text = ""
            # Check first 3 pages for DOI
            for i in range(min(3, len(doc))):
                text += doc[i].get_text()
            doc.close()

            # Find DOI
            doi = self._extract_doi(text)
            if not doi:
                return DocumentMetadata(extractor=self.name)

            # Query CrossRef API
            return self.query_crossref(doi)

        except Exception:
            return DocumentMetadata(extractor=self.name)

    def _extract_doi(self, text: str) -> str | None:
        """Extract DOI from text.

        Args:
            text: Text to search for DOI

        Returns:
            DOI string or None
        """
        # DOI pattern: 10.xxxx/...
        doi_pattern = r"10\.\d{4,}/[^\s]+"
        match = re.search(doi_pattern, text)

        if match:
            doi = match.group()
            # Clean up common trailing characters
            return doi.rstrip(".,;)")

        return None

    def query_crossref(self, doi: str) -> DocumentMetadata:
        """Query CrossRef API for DOI metadata.

        Args:
            doi: DOI to look up

        Returns:
            DocumentMetadata with CrossRef data
        """
        try:
            url = f"https://api.crossref.org/works/{doi}"
            headers = {"User-Agent": "MetadataExtractor/1.0"}
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code != 200:
                # Raise exception for rate limiting or service unavailability
                raise CrossRefUnavailableError(
                    f"CrossRef API returned status {response.status_code}. "
                    f"May be rate-limiting or temporarily unavailable."
                )

            data = response.json()
            message = data.get("message", {})
            return self._parse_message(message, self.name)

        except Exception:
            return DocumentMetadata(extractor=self.name)

    def search_by_title(self, title: str) -> DocumentMetadata:
        """Search CrossRef by bibliographic title with strict validation.

        A hit is accepted only when its title strongly matches the query title.
        On rate limiting (429/503) or any error, empty metadata is returned so
        the resolver keeps going and a later re-run can retry.

        Args:
            title: Candidate title to search for

        Returns:
            DocumentMetadata for a validated match, else empty metadata
        """
        try:
            response = requests.get(
                _CROSSREF_SEARCH_URL,
                params={"query.bibliographic": title, "rows": "3"},
                headers={"User-Agent": _CROSSREF_USER_AGENT},
                timeout=10,
            )
            if response.status_code != 200:
                return DocumentMetadata(extractor=_CROSSREF_TITLE_SOURCE)

            items = response.json().get("message", {}).get("items", [])
            for item in items:
                meta = self._parse_message(item, _CROSSREF_TITLE_SOURCE)
                if meta.title and titles_match(title, meta.title):
                    return meta
            return DocumentMetadata(extractor=_CROSSREF_TITLE_SOURCE)

        except Exception:
            return DocumentMetadata(extractor=_CROSSREF_TITLE_SOURCE)

    def _parse_message(self, message: dict, extractor: str) -> DocumentMetadata:
        """Convert a CrossRef work message into DocumentMetadata."""
        title = None
        if message.get("title"):
            title = message["title"][0]

        authors = []
        for author in message.get("author", []):
            given = author.get("given", "")
            family = author.get("family", "")
            if family:
                name = f"{given} {family}".strip() if given else family
                authors.append(name)

        year = None
        if "published" in message:
            date_parts = message["published"].get("date-parts", [[]])[0]
            if date_parts:
                year = date_parts[0]
        elif "published-print" in message:
            date_parts = message["published-print"].get("date-parts", [[]])[0]
            if date_parts:
                year = date_parts[0]

        journal = None
        if message.get("container-title"):
            journal = message["container-title"][0]

        return DocumentMetadata(
            doc_type=message.get("type"),
            title=title,
            authors=authors or None,
            year=year,
            journal=journal,
            page_count=None,
            extractor=extractor,
        )
