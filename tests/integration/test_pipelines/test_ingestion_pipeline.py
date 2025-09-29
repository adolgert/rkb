"""Integration tests for ingestion pipeline."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from rkb.core.document_registry import DocumentRegistry
from rkb.core.models import DocumentStatus, EmbeddingResult, ExtractionResult
from rkb.pipelines.ingestion_pipeline import IngestionPipeline


class TestIngestionPipeline:
    """Integration tests for IngestionPipeline."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        registry = DocumentRegistry(db_path)
        yield registry

        # Cleanup
        if db_path.exists():
            db_path.unlink()

    @pytest.fixture
    def mock_extractor(self):
        """Create mock extractor."""
        extractor = Mock()
        extractor.name = "mock_extractor"
        extractor.version = "1.0.0"

        # Mock successful extraction
        extraction_result = ExtractionResult(
            extractor_name="mock_extractor",
            extractor_version="1.0.0",
            content="This is test content for extraction. " * 50,  # Long enough for chunking
            page_count=1,
        )
        extractor.extract.return_value = extraction_result

        return extractor

    @pytest.fixture
    def mock_embedder(self):
        """Create mock embedder."""
        embedder = Mock()
        embedder.name = "mock_embedder"
        embedder.version = "1.0.0"

        # Mock successful embedding
        def mock_embed(text_chunks):
            return EmbeddingResult(
                embedder_name="mock_embedder",
                embeddings=[[0.1, 0.2, 0.3] for _ in text_chunks],
                chunk_count=len(text_chunks),
            )

        embedder.embed.side_effect = mock_embed
        return embedder

    @pytest.fixture
    def sample_pdf(self):
        """Create a sample PDF file for testing."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"Sample PDF content")
            pdf_path = Path(f.name)

        yield pdf_path

        # Cleanup
        if pdf_path.exists():
            pdf_path.unlink()

    def test_process_single_document_success(self, temp_db, mock_extractor, mock_embedder, sample_pdf):
        """Test successful processing of a single document."""
        with patch("rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor), \
             patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):

            pipeline = IngestionPipeline(
                registry=temp_db,
                extractor_name="mock_extractor",
                embedder_name="mock_embedder",
                project_id="test_project",
            )

            result = pipeline.process_single_document(sample_pdf)

            # Check result
            assert result["status"] == "success"
            assert result["source_path"] == str(sample_pdf)
            assert "doc_id" in result
            assert "extraction_id" in result
            assert result["chunk_count"] > 0
            assert result["processing_time"] >= 0

            # Check database state
            doc = temp_db.get_document(result["doc_id"])
            assert doc is not None
            assert doc.status == DocumentStatus.INDEXED
            assert doc.source_path == sample_pdf

            # Check extraction was called with source_path and doc_id
            assert mock_extractor.extract.call_count == 1
            call_args = mock_extractor.extract.call_args
            assert call_args[0][0] == sample_pdf  # source_path
            assert len(call_args[0][1]) == 36  # doc_id is UUID (36 chars)

            # Check embedder was called
            assert mock_embedder.embed.called

    def test_process_single_document_missing_file(self, temp_db, mock_extractor, mock_embedder):
        """Test processing of non-existent file."""
        with patch("rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor), \
             patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):

            pipeline = IngestionPipeline(
                registry=temp_db,
                extractor_name="mock_extractor",
                embedder_name="mock_embedder",
            )

            missing_file = Path("/nonexistent/file.pdf")
            result = pipeline.process_single_document(missing_file)

            assert result["status"] == "error"
            assert "File not found" in result["message"]

            # Extractor should not be called
            mock_extractor.extract.assert_not_called()

    def test_process_single_document_already_exists(self, temp_db, mock_extractor, mock_embedder, sample_pdf):
        """Test processing of document that already exists."""
        with patch("rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor), \
             patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):

            # Add document to registry first using the new deduplication method
            doc, _ = temp_db.process_new_document(sample_pdf, "test")
            temp_db.update_document_status(doc.doc_id, DocumentStatus.INDEXED)

            pipeline = IngestionPipeline(
                registry=temp_db,
                extractor_name="mock_extractor",
                embedder_name="mock_embedder",
            )

            result = pipeline.process_single_document(sample_pdf, force_reprocess=False)

            assert result["status"] == "skipped"
            assert "already" in result["message"].lower()

            # Extractor should not be called
            mock_extractor.extract.assert_not_called()

    def test_process_batch_from_list(self, temp_db, mock_extractor, mock_embedder, sample_pdf):
        """Test batch processing from file list."""
        with patch("rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor), \
             patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):

            pipeline = IngestionPipeline(
                registry=temp_db,
                extractor_name="mock_extractor",
                embedder_name="mock_embedder",
                project_id="test_batch",
            )

            # Process batch with single file
            file_list = [str(sample_pdf)]
            results = pipeline.process_batch(file_list)

            assert len(results) == 1
            assert results[0]["status"] == "success"

            # Check extraction was called
            mock_extractor.extract.assert_called_once()

    def test_process_batch_with_max_files(self, temp_db, mock_extractor, mock_embedder):
        """Test batch processing with max_files limit."""
        with patch("rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor), \
             patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):

            pipeline = IngestionPipeline(
                registry=temp_db,
                extractor_name="mock_extractor",
                embedder_name="mock_embedder",
            )

            # Create list of 5 fake files
            file_list = [f"/fake/file{i}.pdf" for i in range(5)]

            # Process with max_files=2
            results = pipeline.process_batch(file_list, max_files=2)

            # Should only process 2 files
            assert len(results) == 2
            # Both should fail since files don't exist
            assert all(r["status"] == "error" for r in results)

    def test_get_processing_stats(self, temp_db, mock_extractor, mock_embedder, sample_pdf):
        """Test getting processing statistics."""
        with patch("rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor), \
             patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):

            pipeline = IngestionPipeline(
                registry=temp_db,
                extractor_name="mock_extractor",
                embedder_name="mock_embedder",
                project_id="test_stats",
            )

            # Process a document first
            pipeline.process_single_document(sample_pdf)

            # Get stats
            stats = pipeline.get_processing_stats()

            assert "total_documents" in stats
            assert "extractor" in stats
            assert "embedder" in stats
            assert "project_id" in stats
            assert stats["extractor"] == "mock_extractor"
            assert stats["embedder"] == "mock_embedder"
            assert stats["project_id"] == "test_stats"

    def test_list_documents_by_project(self, temp_db, mock_extractor, mock_embedder, sample_pdf):
        """Test listing documents by project."""
        with patch("rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor), \
             patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):

            pipeline = IngestionPipeline(
                registry=temp_db,
                extractor_name="mock_extractor",
                embedder_name="mock_embedder",
                project_id="test_list",
            )

            # Process a document
            pipeline.process_single_document(sample_pdf)

            # List documents
            documents = pipeline.list_documents()

            assert len(documents) == 1
            assert documents[0].source_path == sample_pdf
            assert documents[0].status == DocumentStatus.INDEXED

    def test_retry_failed_documents(self, temp_db, mock_extractor, mock_embedder, sample_pdf):
        """Test retrying failed documents."""
        with patch("rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor), \
             patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):

            # Create a failed document in the registry using new deduplication method
            doc, _ = temp_db.process_new_document(sample_pdf, "test_retry")
            temp_db.update_document_status(doc.doc_id, DocumentStatus.FAILED)

            pipeline = IngestionPipeline(
                registry=temp_db,
                extractor_name="mock_extractor",
                embedder_name="mock_embedder",
                project_id="test_retry",
            )

            # Retry failed documents
            results = pipeline.retry_failed_documents()

            assert len(results) == 1
            assert results[0]["status"] == "success"

            # Document should now be indexed (complete)
            updated_doc = temp_db.get_document(doc.doc_id)
            assert updated_doc.status == DocumentStatus.INDEXED
