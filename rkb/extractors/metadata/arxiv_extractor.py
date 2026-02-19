"""Extract metadata using the arXiv API."""

import re
from pathlib import Path

from rkb.extractors.metadata.base import MetadataExtractor
from rkb.extractors.metadata.models import DocumentMetadata

_ARXIV_FILENAME_RE = re.compile(r"(\d{4}\.\d{4,5})")


class ArxivExtractor(MetadataExtractor):
    """Extract metadata from arXiv API given an arXiv ID."""

    @property
    def name(self) -> str:
        return "arxiv"

    def extract(self, pdf_path: Path) -> DocumentMetadata:
        """Try to detect arXiv ID from filename and query API."""
        arxiv_id = self.id_from_filename(pdf_path.name)
        if arxiv_id:
            return self.extract_by_id(arxiv_id)
        return DocumentMetadata(extractor=self.name)

    def extract_by_id(self, arxiv_id: str) -> DocumentMetadata:
        """Query arXiv Client API for metadata by arXiv ID."""
        try:
            import arxiv

            client = arxiv.Client()
            search = arxiv.Search(id_list=[arxiv_id])
            results = list(client.results(search))
            if not results:
                return DocumentMetadata(extractor=self.name)

            paper = results[0]
            authors = [a.name for a in paper.authors] if paper.authors else None
            year = paper.published.year if paper.published else None
            abstract = paper.summary.strip() if paper.summary else None
            categories = list(paper.categories) if paper.categories else None

            return DocumentMetadata(
                title=paper.title,
                authors=authors,
                year=year,
                abstract=abstract,
                journal=", ".join(categories) if categories else None,
                extractor=self.name,
            )
        except Exception:
            return DocumentMetadata(extractor=self.name)

    @staticmethod
    def id_from_filename(filename: str) -> str | None:
        """Extract arXiv ID from filename like 2301.12345.pdf."""
        match = _ARXIV_FILENAME_RE.search(filename)
        return match.group(1) if match else None
