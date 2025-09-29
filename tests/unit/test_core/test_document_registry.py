"""Tests for DocumentRegistry content hash and deduplication functionality."""

import tempfile
from pathlib import Path

import pytest

from rkb.core.document_registry import DocumentRegistry
from rkb.core.models import Document


class TestDocumentRegistryDeduplication:
    """Test DocumentRegistry deduplication functionality."""

    @pytest.fixture
    def temp_registry(self):
        """Create temporary registry for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
            registry = DocumentRegistry(db_path)
            yield registry
            # Cleanup
            registry.close()
            db_path.unlink()

    @pytest.fixture
    def sample_files(self):
        """Create sample files with known content."""
        files = {}

        # Create file with content "test content 1"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pdf", delete=False) as f:
            f.write("test content 1")
            f.flush()
            files["file1"] = Path(f.name)

        # Create file with same content "test content 1"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pdf", delete=False) as f:
            f.write("test content 1")
            f.flush()
            files["duplicate"] = Path(f.name)

        # Create file with different content
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pdf", delete=False) as f:
            f.write("test content 2")
            f.flush()
            files["file2"] = Path(f.name)

        yield files

        # Cleanup
        for file_path in files.values():
            file_path.unlink()

    def test_find_by_content_hash(self, temp_registry, sample_files):
        """Test finding document by content hash."""
        # Add a document
        doc, is_new = temp_registry.process_new_document(sample_files["file1"])
        assert is_new
        assert doc.content_hash

        # Find by content hash
        found_doc = temp_registry.find_by_content_hash(doc.content_hash)
        assert found_doc is not None
        assert found_doc.doc_id == doc.doc_id
        assert found_doc.content_hash == doc.content_hash

        # Search for non-existent hash
        not_found = temp_registry.find_by_content_hash("nonexistent_hash")
        assert not_found is None

    def test_process_new_document_deduplication(self, temp_registry, sample_files):
        """Test that duplicate content is detected."""
        # Process first file
        doc1, is_new1 = temp_registry.process_new_document(sample_files["file1"])
        assert is_new1
        assert doc1.content_hash

        # Process duplicate content file
        doc2, is_new2 = temp_registry.process_new_document(sample_files["duplicate"])
        assert not is_new2  # Should not be new
        assert doc2.doc_id == doc1.doc_id  # Same document
        assert doc2.content_hash == doc1.content_hash

        # Process different content file
        doc3, is_new3 = temp_registry.process_new_document(sample_files["file2"])
        assert is_new3  # Should be new
        assert doc3.doc_id != doc1.doc_id  # Different document
        assert doc3.content_hash != doc1.content_hash

    def test_multiple_source_paths_same_content(self, temp_registry, sample_files):
        """Test that multiple documents can reference same content hash."""
        # Process both files with same content
        doc1, _ = temp_registry.process_new_document(sample_files["file1"])
        doc2, _ = temp_registry.process_new_document(sample_files["duplicate"])

        # Should be same document
        assert doc1.doc_id == doc2.doc_id
        assert doc1.content_hash == doc2.content_hash

        # Both should be findable by content hash
        found_doc = temp_registry.find_by_content_hash(doc1.content_hash)
        assert found_doc.doc_id == doc1.doc_id

    def test_update_document_content_hash(self, temp_registry):
        """Test updating document content hash."""
        # Create a document without going through process_new_document
        doc = Document(source_path=Path("/fake/path.pdf"))
        temp_registry.add_document(doc)

        # Update content hash
        new_hash = "updated_hash_value"
        success = temp_registry.update_document_content_hash(doc.doc_id, new_hash)
        assert success

        # Verify update
        retrieved_doc = temp_registry.get_document(doc.doc_id)
        assert retrieved_doc.content_hash == new_hash

        # Test updating non-existent document
        no_update = temp_registry.update_document_content_hash("fake_id", "hash")
        assert not no_update

    def test_get_all_documents(self, temp_registry, sample_files):
        """Test getting all documents."""
        # Initially empty
        all_docs = temp_registry.get_all_documents()
        assert len(all_docs) == 0

        # Add some documents
        temp_registry.process_new_document(sample_files["file1"])
        temp_registry.process_new_document(sample_files["file2"])

        # Should have 2 unique documents (duplicate should not create new)
        all_docs = temp_registry.get_all_documents()
        assert len(all_docs) == 2

        # Verify they have different content hashes
        hashes = {doc.content_hash for doc in all_docs}
        assert len(hashes) == 2

    def test_process_new_document_with_project_id(self, temp_registry, sample_files):
        """Test processing document with project ID."""
        project_id = "test_project_123"

        doc, is_new = temp_registry.process_new_document(
            sample_files["file1"],
            project_id=project_id
        )

        assert is_new
        assert doc.project_id == project_id

        # Verify it's stored correctly
        retrieved = temp_registry.get_document(doc.doc_id)
        assert retrieved.project_id == project_id
