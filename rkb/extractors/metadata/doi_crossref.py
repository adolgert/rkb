"""Extract metadata using DOI and CrossRef API."""

import re
from pathlib import Path

import pymupdf
import requests

from rkb.extractors.metadata.base import MetadataExtractor
from rkb.extractors.metadata.models import DocumentMetadata


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
            return self._query_crossref(doi)

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

    def _query_crossref(self, doi: str) -> DocumentMetadata:
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

            # Extract title
            title = None
            if message.get("title"):
                title = message["title"][0]

            # Extract authors
            authors = []
            for author in message.get("author", []):
                given = author.get("given", "")
                family = author.get("family", "")
                if family:
                    name = f"{given} {family}".strip() if given else family
                    authors.append(name)

            # Extract year
            year = None
            if "published" in message:
                date_parts = message["published"].get("date-parts", [[]])[0]
                if date_parts:
                    year = date_parts[0]
            elif "published-print" in message:
                date_parts = message["published-print"].get("date-parts", [[]])[0]
                if date_parts:
                    year = date_parts[0]

            # Extract journal/venue
            journal = None
            if message.get("container-title"):
                journal = message["container-title"][0]

            # Extract document type
            doc_type = message.get("type")

            return DocumentMetadata(
                doc_type=doc_type,
                title=title,
                authors=authors if authors else None,
                year=year,
                journal=journal,
                page_count=None,
                extractor=self.name,
            )

        except Exception:
            return DocumentMetadata(extractor=self.name)
