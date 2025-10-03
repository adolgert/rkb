"""Extract metadata by parsing the first page of a PDF."""

import re
from pathlib import Path

import pymupdf

from rkb.extractors.metadata.base import MetadataExtractor
from rkb.extractors.metadata.models import DocumentMetadata


class FirstPageParser(MetadataExtractor):
    """Extract metadata from first page text and formatting."""

    @property
    def name(self) -> str:
        return "first_page"

    def extract(self, pdf_path: Path) -> DocumentMetadata:
        """Extract metadata from first page.

        Args:
            pdf_path: Path to PDF file

        Returns:
            DocumentMetadata with fields extracted from first page
        """
        try:
            doc = pymupdf.open(pdf_path)
            if len(doc) == 0:
                doc.close()
                return DocumentMetadata(extractor=self.name)

            page = doc[0]
            text = page.get_text()
            doc.close()

            # Extract title (usually first 1-3 lines, often in larger font)
            title = self._extract_title(text)

            # Extract authors
            authors = self._extract_authors(text)

            # Extract year
            year = self._extract_year(text)

            # Extract venue/journal
            journal = self._extract_journal(text)

            return DocumentMetadata(
                doc_type=None,
                title=title,
                authors=authors,
                year=year,
                journal=journal,
                page_count=None,
                extractor=self.name,
            )

        except Exception:
            return DocumentMetadata(extractor=self.name)

    def _extract_title(self, text: str) -> str | None:
        """Extract title from first page text."""
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if not lines:
            return None

        # Title is usually in first few lines
        # Take first non-empty line that's not too short
        for line in lines[:5]:
            if len(line) > 10 and not line.isupper():  # Avoid headers
                return line

        return lines[0] if lines else None

    def _extract_authors(self, text: str) -> list[str] | None:
        """Extract authors from first page text."""
        # Look for common author patterns (e.g., "Firstname Lastname" or "F. Lastname")
        author_pattern = r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b|\b[A-Z]\.\s*[A-Z][a-z]+\b"
        matches = re.findall(author_pattern, text[:500])  # Check first 500 chars

        if matches:
            # Filter out common false positives
            stopwords = {"The", "And", "For", "With", "From"}
            authors = [m for m in matches if m.split()[0] not in stopwords]
            return authors[:5] if authors else None  # Limit to first 5

        return None

    def _extract_year(self, text: str) -> int | None:
        """Extract year from first page text."""
        # Look for 4-digit year in first 1000 characters
        year_matches = re.findall(r"\b(19|20)\d{2}\b", text[:1000])

        if year_matches:
            # Return the first valid year
            for year_str in year_matches:
                try:
                    year = int(year_str)
                    if 1900 <= year <= 2100:
                        return year
                except ValueError:
                    pass

        return None

    def _extract_journal(self, text: str) -> str | None:
        """Extract journal/conference name from first page."""
        # Common patterns for journal/conference names
        patterns = [
            r"(?:Published in|Proceedings of|In)\s+([A-Z][^\n]{10,80})",
            r"([A-Z][a-z]+\s+(?:Journal|Conference|Proceedings)[^\n]{0,60})",
        ]

        for pattern in patterns:
            match = re.search(pattern, text[:1000])
            if match:
                venue = match.group(1).strip()
                # Clean up
                venue = re.sub(r"\s+", " ", venue)
                if len(venue) > 5:
                    return venue

        return None
