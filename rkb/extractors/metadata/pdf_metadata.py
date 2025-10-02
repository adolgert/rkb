"""Extract metadata from PDF built-in metadata fields."""

from pathlib import Path

import pymupdf

from rkb.extractors.metadata.base import MetadataExtractor
from rkb.extractors.metadata.models import DocumentMetadata


class PDFMetadataExtractor(MetadataExtractor):
    """Extract metadata from PDF built-in metadata fields using pymupdf."""

    @property
    def name(self) -> str:
        return "pdf_metadata"

    def extract(self, pdf_path: Path) -> DocumentMetadata:
        """Extract metadata from PDF metadata fields.

        Args:
            pdf_path: Path to PDF file

        Returns:
            DocumentMetadata with available fields populated
        """
        try:
            doc = pymupdf.open(pdf_path)
            metadata = doc.metadata
            page_count = len(doc)
            doc.close()

            # Extract authors - PDF metadata usually has single author string
            author_str = metadata.get("author", "")
            authors = [author_str] if author_str else None

            # Try to extract year from creation date or mod date
            year = None
            for date_field in ["creationDate", "modDate"]:
                date_str = metadata.get(date_field, "")
                if date_str and len(date_str) >= 4:
                    # PDF dates are like "D:20230101..." or just "2023"
                    year_match = date_str[2:6] if date_str.startswith("D:") else date_str[:4]
                    try:
                        year = int(year_match)
                        break
                    except ValueError:
                        pass

            return DocumentMetadata(
                doc_type=None,  # Not available in PDF metadata
                title=metadata.get("title") or None,
                authors=authors,
                year=year,
                journal=metadata.get("subject") or None,  # Subject sometimes contains journal
                page_count=page_count,
                extractor=self.name,
            )

        except Exception:
            # Return empty metadata on error
            return DocumentMetadata(extractor=self.name)
