"""Base class for metadata extractors."""

from abc import ABC, abstractmethod
from pathlib import Path

from rkb.extractors.metadata.models import DocumentMetadata


class MetadataExtractor(ABC):
    """Abstract base class for metadata extractors."""

    @abstractmethod
    def extract(self, pdf_path: Path) -> DocumentMetadata:
        """Extract metadata from a PDF file.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            DocumentMetadata object with extracted fields
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this extractor."""
