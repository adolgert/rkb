"""Extract metadata from PDF filename using pattern matching."""

import contextlib
import re
from pathlib import Path

from rkb.extractors.metadata.base import MetadataExtractor
from rkb.extractors.metadata.models import DocumentMetadata


class FilenameExtractor(MetadataExtractor):
    """Extract metadata from filename patterns."""

    @property
    def name(self) -> str:
        return "filename"

    def extract(self, pdf_path: Path) -> DocumentMetadata:
        """Extract metadata from filename.

        Args:
            pdf_path: Path to PDF file

        Returns:
            DocumentMetadata with fields extracted from filename
        """
        filename = pdf_path.stem  # Filename without extension

        # Try to extract year
        year = None
        # Look for 4-digit year
        year_match = re.search(r"(19|20)\d{2}", filename)
        if year_match:
            with contextlib.suppress(ValueError):
                year = int(year_match.group())

        # Try to extract author from start of filename
        authors = None
        # Look for capitalized word at start (e.g., "Smith2023_...")
        author_match = re.match(r"^([A-Z][a-z]+)", filename)
        if author_match:
            authors = [author_match.group(1)]

        # Check for arXiv pattern
        arxiv_match = re.search(r"(\d{4})\.(\d+)", filename)
        if arxiv_match and not year:
            # First part of arXiv ID can be year (e.g., 2301.12345)
            try:
                potential_year = int(arxiv_match.group(1))
                if 1900 <= potential_year <= 2100:
                    year = potential_year
            except ValueError:
                pass

        return DocumentMetadata(
            doc_type=None,
            title=None,
            authors=authors,
            year=year,
            journal=None,
            page_count=None,
            extractor=self.name,
        )
