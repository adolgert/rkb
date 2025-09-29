"""Centralized path resolution for all RKB storage."""

from pathlib import Path


class PathResolver:
    """Static methods for consistent path generation."""

    @staticmethod
    def get_extraction_dir(doc_id: str, base_dir: Path = Path("extractions")) -> Path:
        """Get document extraction directory.

        Args:
            doc_id: Document identifier
            base_dir: Base directory for extractions

        Returns:
            Path to document extraction directory
        """
        return base_dir / "documents" / doc_id

    @staticmethod
    def get_extraction_path(doc_id: str, base_dir: Path = Path("extractions")) -> Path:
        """Get path for extracted content file.

        Args:
            doc_id: Document identifier
            base_dir: Base directory for extractions

        Returns:
            Path to extracted content file
        """
        return PathResolver.get_extraction_dir(doc_id, base_dir) / "extracted.mmd"

    @staticmethod
    def get_metadata_path(doc_id: str, base_dir: Path = Path("extractions")) -> Path:
        """Get path for document metadata file.

        Args:
            doc_id: Document identifier
            base_dir: Base directory for extractions

        Returns:
            Path to document metadata file
        """
        return PathResolver.get_extraction_dir(doc_id, base_dir) / "metadata.json"

    @staticmethod
    def ensure_extraction_dir(doc_id: str, base_dir: Path = Path("extractions")) -> Path:
        """Create extraction directory if it doesn't exist.

        Args:
            doc_id: Document identifier
            base_dir: Base directory for extractions

        Returns:
            Path to created extraction directory
        """
        extract_dir = PathResolver.get_extraction_dir(doc_id, base_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)
        return extract_dir
