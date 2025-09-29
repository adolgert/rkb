"""Tests for IngestionPipeline deduplication functionality."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from rkb.core.document_registry import DocumentRegistry
from rkb.core.models import DocumentStatus, ExtractionResult, ExtractionStatus
from rkb.pipelines.ingestion_pipeline import IngestionPipeline


class TestIngestionPipelineDeduplication:
    """Test IngestionPipeline deduplication functionality."""

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
        extractor = Mock()
        extractor.extract.return_value = ExtractionResult(
            extraction_id="test-extraction",
            status=ExtractionStatus.COMPLETE,
            content="Extracted content",
            extractor_name="mock_extractor",
            extractor_version="1.0.0"
        )
        return extractor

    @pytest.fixture
    def mock_embedder(self):
        """Create mock embedder."""
        embedder = Mock()
        embedder.embed.return_value = Mock(
            embedding_id="test-embedding",
            chunk_count=5,
            error_message=None
        )
        return embedder

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

    def test_process_single_document_new_file(
        self, temp_registry, mock_extractor, mock_embedder, sample_files
    ):
        """Test processing a new document."""
        with patch("rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor), \
             patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):

            pipeline = IngestionPipeline(
                registry=temp_registry,
                project_id="test_project"
            )

            result = pipeline.process_single_document(sample_files["file1"])

            assert result["status"] == "success"
            assert "doc_id" in result
            assert result["source_path"] == str(sample_files["file1"])

            # Verify extractor was called with doc_id
            mock_extractor.extract.assert_called_once()
            call_args = mock_extractor.extract.call_args
            assert call_args[0][0] == sample_files["file1"]  # source_path
            assert len(call_args[0]) == 2  # source_path and doc_id
            assert len(call_args[0][1]) == 36  # doc_id is UUID

    def test_process_single_document_duplicate_content(
        self, temp_registry, mock_extractor, mock_embedder, sample_files
    ):
        """Test processing duplicate content."""
        with patch("rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor), \
             patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):

            pipeline = IngestionPipeline(
                registry=temp_registry,
                project_id="test_project"
            )

            # Process first file
            result1 = pipeline.process_single_document(sample_files["file1"])
            assert result1["status"] == "success"
            doc_id_1 = result1["doc_id"]

            # Process duplicate content file
            result2 = pipeline.process_single_document(sample_files["duplicate"])

            # Should be skipped as already fully processed
            # (Since the first file completed successfully and went to INDEXED status)
            assert result2["status"] == "skipped"
            assert result2["doc_id"] == doc_id_1  # Same document ID
            assert "already fully processed" in result2["message"]

            # Extractor should only be called once (for the first file)
            assert mock_extractor.extract.call_count == 1

    def test_process_single_document_different_content(
        self, temp_registry, mock_extractor, mock_embedder, sample_files
    ):
        """Test processing files with different content."""
        with patch("rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor), \
             patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):

            pipeline = IngestionPipeline(
                registry=temp_registry,
                project_id="test_project"
            )

            # Process first file
            result1 = pipeline.process_single_document(sample_files["file1"])
            assert result1["status"] == "success"
            doc_id_1 = result1["doc_id"]

            # Process different content file
            result2 = pipeline.process_single_document(sample_files["file2"])

            # Should be processed as new
            assert result2["status"] == "success"
            assert result2["doc_id"] != doc_id_1  # Different document ID

            # Extractor should be called twice
            assert mock_extractor.extract.call_count == 2

    def test_process_single_document_force_reprocess_duplicate(
        self, temp_registry, mock_extractor, mock_embedder, sample_files
    ):
        """Test force reprocessing of duplicate content."""
        with patch("rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor), \
             patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):

            pipeline = IngestionPipeline(
                registry=temp_registry,
                project_id="test_project"
            )

            # Process first file
            result1 = pipeline.process_single_document(sample_files["file1"])
            assert result1["status"] == "success"

            # Force reprocess duplicate
            result2 = pipeline.process_single_document(
                sample_files["duplicate"],
                force_reprocess=True
            )

            # Should be reprocessed despite being duplicate
            assert result2["status"] == "success"

            # Extractor should be called twice due to force_reprocess
            assert mock_extractor.extract.call_count == 2

    def test_process_single_document_doc_id_passed_to_extractor(
        self, temp_registry, mock_extractor, mock_embedder, sample_files
    ):
        """Test that doc_id is correctly passed to extractor."""
        with patch("rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor), \
             patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):

            pipeline = IngestionPipeline(
                registry=temp_registry,
                project_id="test_project"
            )

            result = pipeline.process_single_document(sample_files["file1"])

            # Verify extractor was called with the correct doc_id
            mock_extractor.extract.assert_called_once()
            call_args = mock_extractor.extract.call_args
            source_path, doc_id = call_args[0]

            assert source_path == sample_files["file1"]
            assert doc_id == result["doc_id"]
            assert len(doc_id) == 36  # UUID length

    def test_process_single_document_skips_already_indexed(
        self, temp_registry, mock_extractor, mock_embedder, sample_files
    ):
        """Test that already indexed documents are skipped."""
        with patch("rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor), \
             patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):

            pipeline = IngestionPipeline(
                registry=temp_registry,
                project_id="test_project"
            )

            # Process and complete a document
            result1 = pipeline.process_single_document(sample_files["file1"])
            assert result1["status"] == "success"

            # Mark as indexed
            temp_registry.update_document_status(result1["doc_id"], DocumentStatus.INDEXED)

            # Try to process same file again (different path, same content)
            result2 = pipeline.process_single_document(sample_files["duplicate"])

            # Should be skipped as already fully processed
            assert result2["status"] == "skipped"
            assert "already fully processed" in result2["message"]

            # Extractor should only be called once
            assert mock_extractor.extract.call_count == 1

    def test_process_single_document_duplicate_not_fully_processed(
        self, temp_registry, mock_extractor, mock_embedder, sample_files
    ):
        """Test processing duplicate when original is not fully processed."""
        with patch("rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor), \
             patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):

            pipeline = IngestionPipeline(
                registry=temp_registry,
                project_id="test_project",
                skip_embedding=True  # Skip embedding to keep status as EXTRACTED
            )

            # Process first file (will be EXTRACTED, not INDEXED due to skip_embedding)
            result1 = pipeline.process_single_document(sample_files["file1"])
            assert result1["status"] == "success"
            doc_id_1 = result1["doc_id"]

            # Process duplicate content file
            result2 = pipeline.process_single_document(sample_files["duplicate"])

            # Should be detected as duplicate (not skipped since not INDEXED)
            assert result2["status"] == "duplicate"
            assert result2["doc_id"] == doc_id_1  # Same document ID
            assert "content hash" in result2["message"]
            assert "content_hash" in result2

            # Extractor should only be called once (for the first file)
            assert mock_extractor.extract.call_count == 1
