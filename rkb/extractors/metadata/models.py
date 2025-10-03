"""Data models for document metadata."""

from dataclasses import dataclass


@dataclass
class DocumentMetadata:
    """Metadata extracted from an academic document.

    Attributes:
        doc_type: Document type (article, inproceedings, report, book, etc.)
        title: Document title
        authors: List of author names
        year: Publication year
        journal: Journal or conference name
        page_count: Number of pages in document
        extractor: Name of the extractor that produced this metadata
    """

    doc_type: str | None = None
    title: str | None = None
    authors: list[str] | None = None
    year: int | None = None
    journal: str | None = None
    page_count: int | None = None
    extractor: str = ""

    def format_line1(self) -> str:
        """Format first line: first_author, "title"."""
        first_author = self.authors[0] if self.authors else "unknown"
        title = f'"{self.title}"' if self.title else "unknown"
        return f"{first_author}, {title}"

    def format_line2(self) -> str:
        """Format second line: year, document_type, journal, page_count."""
        year = str(self.year) if self.year else "unknown"
        doc_type = self.doc_type if self.doc_type else "unknown"
        journal = self.journal if self.journal else "unknown"
        page_count = str(self.page_count) if self.page_count else "unknown"
        return f"{year}, {doc_type}, {journal}, {page_count}"
