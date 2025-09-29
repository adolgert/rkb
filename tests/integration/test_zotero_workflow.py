"""Integration test for Zotero storage workflow."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rkb.core.document_registry import DocumentRegistry
from rkb.pipelines.ingestion_pipeline import IngestionPipeline


class TestZoteroWorkflow:
    """Test full workflow with Zotero-like structure."""

    @pytest.fixture
    def zotero_structure(self):
        """Create mock Zotero storage structure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)

            # Create Zotero-like structure
            storage_dir = base_dir / "Zotero" / "storage"

            # Create multiple papers with same filename
            (storage_dir / "ABC123").mkdir(parents=True)
            (storage_dir / "ABC123" / "Document.pdf").write_bytes(b"Content of paper 1")

            (storage_dir / "XYZ789").mkdir(parents=True)
            (storage_dir / "XYZ789" / "Document.pdf").write_bytes(b"Content of paper 2")

            # Create identical content in different locations
            (storage_dir / "DEF456").mkdir(parents=True)
            (storage_dir / "DEF456" / "Paper.pdf").write_bytes(b"Content of paper 1")  # Duplicate

            yield storage_dir

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
    def mock_extractor(self):
        """Create mock extractor."""
        from rkb.core.models import ExtractionResult, ExtractionStatus

        extractor = MagicMock()

        def mock_extract(source_path, doc_id=None):
            return ExtractionResult(
                doc_id=doc_id or "test-doc-id",
                extraction_id="test-extraction",
                status=ExtractionStatus.COMPLETE,
                content="Extracted content",
                extractor_name="mock_extractor",
                extractor_version="1.0.0",
                chunks=["chunk1", "chunk2"],
                chunk_metadata=[],
                page_count=1
            )

        extractor.extract.side_effect = mock_extract
        return extractor

    @pytest.fixture
    def mock_embedder(self):
        """Create mock embedder."""
        from rkb.core.models import EmbeddingResult

        embedder = MagicMock()

        def mock_embed(chunks):
            return EmbeddingResult(
                embedding_id="test-embedding",
                embedder_name="mock_embedder",
                chunk_count=len(chunks),
                error_message=None
            )

        embedder.embed.side_effect = mock_embed
        return embedder

    def test_duplicate_filename_handling(self, zotero_structure, temp_registry):
        """Test that duplicate filenames are handled correctly."""
        # Process both Document.pdf files
        doc1_path = zotero_structure / "ABC123" / "Document.pdf"
        doc2_path = zotero_structure / "XYZ789" / "Document.pdf"

        doc1, is_new1 = temp_registry.process_new_document(doc1_path)
        doc2, is_new2 = temp_registry.process_new_document(doc2_path)

        # Both should be processed as new (different content)
        assert is_new1
        assert is_new2
        assert doc1.doc_id != doc2.doc_id
        assert doc1.content_hash != doc2.content_hash

    def test_content_deduplication(self, zotero_structure, temp_registry):
        """Test that identical content is deduplicated."""
        # Process original and duplicate
        original_path = zotero_structure / "ABC123" / "Document.pdf"
        duplicate_path = zotero_structure / "DEF456" / "Paper.pdf"

        doc1, is_new1 = temp_registry.process_new_document(original_path)
        doc2, is_new2 = temp_registry.process_new_document(duplicate_path)

        # First should be new, second should be duplicate
        assert is_new1
        assert not is_new2
        assert doc1.doc_id == doc2.doc_id  # Same document
        assert doc1.content_hash == doc2.content_hash

    def test_readonly_source_preservation(self, zotero_structure, temp_registry):
        """Test that source directories are never modified."""
        # Get initial state
        initial_files = list(zotero_structure.rglob("*"))
        initial_content = {}
        for f in initial_files:
            if f.is_file():
                initial_content[f] = f.read_bytes()

        # Process documents
        for pdf_file in zotero_structure.rglob("*.pdf"):
            temp_registry.process_new_document(pdf_file)

        # Verify source unchanged
        final_files = list(zotero_structure.rglob("*"))
        assert len(final_files) == len(initial_files)

        for f in initial_files:
            if f.is_file():
                assert f.read_bytes() == initial_content[f]

    def test_zotero_source_detection(self, zotero_structure, temp_registry):
        """Test that Zotero sources are detected correctly."""
        from rkb.core.identity import DocumentIdentity

        doc_path = zotero_structure / "ABC123" / "Document.pdf"
        identity = DocumentIdentity(doc_path)

        assert identity.source_type == "zotero"
        assert identity.zotero_id == "ABC123"

    def test_full_pipeline_with_zotero_structure(
        self, zotero_structure, temp_registry, mock_extractor, mock_embedder
    ):
        """Test full pipeline with Zotero-like directory structure."""
        with patch("rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor), \
             patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):

            pipeline = IngestionPipeline(
                registry=temp_registry,
                project_id="zotero_test"
            )

            results = []
            pdf_files = list(zotero_structure.rglob("*.pdf"))

            for pdf_file in pdf_files:
                result = pipeline.process_single_document(pdf_file)
                results.append(result)

            # Should have 3 PDFs total
            assert len(results) == 3

            # Check results
            success_count = sum(1 for r in results if r["status"] == "success")
            skipped_count = sum(1 for r in results if r["status"] == "skipped")

            # Should have 2 successful and 1 skipped (due to duplication)
            assert success_count == 2
            assert skipped_count == 1

            # All should have doc_ids
            for result in results:
                assert "doc_id" in result

    def test_extraction_paths_use_doc_id(
        self, zotero_structure, temp_registry, mock_extractor, mock_embedder
    ):
        """Test that extraction paths use doc_id instead of filename."""
        with patch("rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor), \
             patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):

            pipeline = IngestionPipeline(
                registry=temp_registry,
                project_id="zotero_test"
            )

            # Process a document
            doc_path = zotero_structure / "ABC123" / "Document.pdf"
            result = pipeline.process_single_document(doc_path)

            assert result["status"] == "success"
            doc_id = result["doc_id"]

            # Verify extractor was called with doc_id
            mock_extractor.extract.assert_called()
            call_args = mock_extractor.extract.call_args
            source_path, passed_doc_id = call_args[0]

            assert source_path == doc_path
            assert passed_doc_id == doc_id
            assert len(doc_id) == 36  # UUID length

    def test_multiple_zotero_documents_different_names(self, temp_registry):
        """Test processing multiple Zotero documents with different content but same filenames."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            storage_dir = base_dir / "Zotero" / "storage"

            # Create multiple Zotero entries with same filename but different content
            entries = [
                ("ENTRY001", b"First research paper content"),
                ("ENTRY002", b"Second research paper content"),
                ("ENTRY003", b"Third research paper content"),
            ]

            for entry_id, content in entries:
                entry_dir = storage_dir / entry_id
                entry_dir.mkdir(parents=True)
                (entry_dir / "research_paper.pdf").write_bytes(content)

            # Process all documents
            documents = []
            for entry_id, _ in entries:
                doc_path = storage_dir / entry_id / "research_paper.pdf"
                doc, is_new = temp_registry.process_new_document(doc_path, "zotero_project")
                documents.append((doc, is_new))

            # All should be new (different content)
            assert all(is_new for _, is_new in documents)

            # All should have different doc_ids and content_hashes
            doc_ids = {doc.doc_id for doc, _ in documents}
            content_hashes = {doc.content_hash for doc, _ in documents}

            assert len(doc_ids) == 3
            assert len(content_hashes) == 3

            # All should be in the same project
            for doc, _ in documents:
                assert doc.project_id == "zotero_project"
