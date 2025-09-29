"""Document identity and path management."""

import hashlib
import uuid
from pathlib import Path


class DocumentIdentity:
    """Manages document identity, content hashing, and storage paths."""

    def __init__(self, source_path: Path, content_hash: str | None = None):
        """Initialize document identity.

        Args:
            source_path: Path to the source document
            content_hash: Pre-computed content hash (optional)
        """
        self.doc_id = str(uuid.uuid4())
        self.source_path = source_path.resolve()
        self.content_hash = content_hash or self._calculate_content_hash()

    def _calculate_content_hash(self) -> str:
        """Calculate SHA-256 hash of file content.

        Returns:
            Hexadecimal representation of SHA-256 hash
        """
        sha256_hash = hashlib.sha256()
        with self.source_path.open("rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    @property
    def source_type(self) -> str:
        """Detect source type from path.

        Returns:
            Source type: 'zotero', 'dropbox', or 'local'
        """
        path_str = str(self.source_path)
        if "Zotero/storage" in path_str:
            return "zotero"
        if "Dropbox" in path_str:
            return "dropbox"
        return "local"

    @property
    def zotero_id(self) -> str | None:
        """Extract Zotero storage ID if applicable.

        Returns:
            Zotero storage directory ID or None
        """
        if self.source_type == "zotero":
            parts = self.source_path.parts
            try:
                storage_idx = parts.index("storage")
                return parts[storage_idx + 1]
            except (ValueError, IndexError):
                return None
        return None

    def get_extraction_path(self, base_dir: Path = Path("extractions")) -> Path:
        """Get path for extracted content.

        Args:
            base_dir: Base directory for extractions

        Returns:
            Path for extracted content file
        """
        return base_dir / "documents" / self.doc_id / "extracted.mmd"

    def get_metadata_path(self, base_dir: Path = Path("extractions")) -> Path:
        """Get path for document metadata.

        Args:
            base_dir: Base directory for extractions

        Returns:
            Path for document metadata file
        """
        return base_dir / "documents" / self.doc_id / "metadata.json"
