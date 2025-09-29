"""Tests for DocumentIdentity and PathResolver."""

import tempfile
from pathlib import Path

from rkb.core.identity import DocumentIdentity
from rkb.core.paths import PathResolver


class TestDocumentIdentity:
    """Test DocumentIdentity functionality."""

    def test_content_hash_calculation(self):
        """Test that content hash is calculated correctly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pdf", delete=False) as f:
            f.write("test content")
            f.flush()
            temp_path = Path(f.name)

            try:
                identity = DocumentIdentity(temp_path)
                assert len(identity.content_hash) == 64  # SHA-256 hex length
                assert identity.content_hash.isalnum()
            finally:
                temp_path.unlink()

    def test_duplicate_content_same_hash(self):
        """Test that identical content produces same hash."""
        content = "identical test content"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".pdf", delete=False) as f1:
            f1.write(content)
            f1.flush()
            temp_path1 = Path(f1.name)

            with tempfile.NamedTemporaryFile(mode="w", suffix=".pdf", delete=False) as f2:
                f2.write(content)
                f2.flush()
                temp_path2 = Path(f2.name)

                try:
                    identity1 = DocumentIdentity(temp_path1)
                    identity2 = DocumentIdentity(temp_path2)

                    assert identity1.content_hash == identity2.content_hash
                    assert identity1.doc_id != identity2.doc_id  # Different doc_ids
                finally:
                    temp_path1.unlink()
                    temp_path2.unlink()

    def test_zotero_source_detection(self):
        """Test Zotero source type detection."""
        # Create a mock DocumentIdentity for testing path detection
        identity = DocumentIdentity.__new__(DocumentIdentity)  # Skip __init__ for test
        identity.source_path = Path("/home/user/Zotero/storage/ABC123/Document.pdf")

        assert identity.source_type == "zotero"
        assert identity.zotero_id == "ABC123"

    def test_dropbox_source_detection(self):
        """Test Dropbox source type detection."""
        identity = DocumentIdentity.__new__(DocumentIdentity)  # Skip __init__ for test
        identity.source_path = Path("/home/user/Dropbox/Papers/Document.pdf")

        assert identity.source_type == "dropbox"
        assert identity.zotero_id is None

    def test_local_source_detection(self):
        """Test local source type detection."""
        identity = DocumentIdentity.__new__(DocumentIdentity)  # Skip __init__ for test
        identity.source_path = Path("/home/user/Documents/Document.pdf")

        assert identity.source_type == "local"
        assert identity.zotero_id is None

    def test_path_generation(self):
        """Test extraction path generation."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pdf", delete=False) as f:
            f.write("test")
            f.flush()
            temp_path = Path(f.name)

            try:
                identity = DocumentIdentity(temp_path)
                extraction_path = identity.get_extraction_path()

                assert "documents" in str(extraction_path)
                assert identity.doc_id in str(extraction_path)
                assert extraction_path.suffix == ".mmd"
            finally:
                temp_path.unlink()

    def test_metadata_path_generation(self):
        """Test metadata path generation."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pdf", delete=False) as f:
            f.write("test")
            f.flush()
            temp_path = Path(f.name)

            try:
                identity = DocumentIdentity(temp_path)
                metadata_path = identity.get_metadata_path()

                assert "documents" in str(metadata_path)
                assert identity.doc_id in str(metadata_path)
                assert metadata_path.suffix == ".json"
            finally:
                temp_path.unlink()


class TestPathResolver:
    """Test PathResolver functionality."""

    def test_path_consistency(self):
        """Test that paths are generated consistently."""
        doc_id = "test-doc-id-123"

        path1 = PathResolver.get_extraction_path(doc_id)
        path2 = PathResolver.get_extraction_path(doc_id)

        assert path1 == path2
        assert doc_id in str(path1)

    def test_extraction_path_structure(self):
        """Test extraction path structure."""
        doc_id = "test-doc-id-456"
        base_path = Path("custom_extractions")

        path = PathResolver.get_extraction_path(doc_id, base_path)

        assert str(path) == f"custom_extractions/documents/{doc_id}/extracted.mmd"
        assert path.suffix == ".mmd"

    def test_metadata_path_structure(self):
        """Test metadata path structure."""
        doc_id = "test-doc-id-789"
        base_path = Path("custom_extractions")

        path = PathResolver.get_metadata_path(doc_id, base_path)

        assert str(path) == f"custom_extractions/documents/{doc_id}/metadata.json"
        assert path.suffix == ".json"

    def test_directory_creation(self):
        """Test directory creation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            doc_id = "test-doc-id-456"
            base_path = Path(temp_dir)

            created_dir = PathResolver.ensure_extraction_dir(doc_id, base_path)

            assert created_dir.exists()
            assert created_dir.is_dir()
            assert doc_id in str(created_dir)
            assert str(created_dir) == f"{temp_dir}/documents/{doc_id}"

    def test_get_extraction_dir(self):
        """Test extraction directory path generation."""
        doc_id = "test-doc-id-999"
        base_path = Path("test_base")

        dir_path = PathResolver.get_extraction_dir(doc_id, base_path)

        assert str(dir_path) == f"test_base/documents/{doc_id}"
