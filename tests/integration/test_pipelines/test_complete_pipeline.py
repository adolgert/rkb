"""Integration tests for complete pipeline."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from rkb.core.document_registry import DocumentRegistry
from rkb.core.models import EmbeddingResult, ExtractionResult
from rkb.pipelines.complete_pipeline import CompletePipeline


class TestCompletePipeline:
    """Integration tests for CompletePipeline."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        registry = DocumentRegistry(db_path)
        yield registry

        # Cleanup
        registry.close()
        if db_path.exists():
            db_path.unlink()

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory with sample PDFs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            data_dir.mkdir()

            # Create sample PDF files
            for i in range(3):
                pdf_file = data_dir / f"sample_{i}.pdf"
                pdf_file.write_bytes(b"Sample PDF content " + str(i).encode())

            yield data_dir

    @pytest.fixture
    def mock_extractor(self):
        """Create mock extractor."""
        extractor = Mock()
        extractor.name = "mock_extractor"
        extractor.version = "1.0.0"

        def mock_extract(source_path, doc_id=None):
            return ExtractionResult(
                extractor_name="mock_extractor",
                extractor_version="1.0.0",
                content=f"Extracted content from {source_path.name}. " * 50,
                page_count=1,
            )

        extractor.extract.side_effect = mock_extract
        extractor.get_capabilities.return_value = {"name": "mock_extractor"}

        return extractor

    @pytest.fixture
    def mock_embedder(self):
        """Create mock embedder."""
        embedder = Mock()
        embedder.name = "mock_embedder"
        embedder.version = "1.0.0"

        def mock_embed(text_chunks):
            return EmbeddingResult(
                embedder_name="mock_embedder",
                embeddings=[[0.1, 0.2, 0.3] for _ in text_chunks],
                chunk_count=len(text_chunks),
            )

        embedder.embed.side_effect = mock_embed
        embedder.get_capabilities.return_value = {"name": "mock_embedder"}

        return embedder

    def test_find_recent_pdfs(self, temp_data_dir):
        """Test finding recent PDF files."""
        pipeline = CompletePipeline()

        files = pipeline.find_recent_pdfs(data_dir=temp_data_dir, num_files=2)

        assert len(files) == 2  # Limited by num_files
        assert all(f["name"].endswith(".pdf") for f in files)
        assert all("path" in f for f in files)
        assert all("size_mb" in f for f in files)
        assert all("modified_date" in f for f in files)

        # Files should be sorted by modification time (most recent first)
        assert files[0]["modified_time"] >= files[1]["modified_time"]

    def test_find_recent_pdfs_with_output_file(self, temp_data_dir):
        """Test finding PDFs with output file."""
        pipeline = CompletePipeline()

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            output_file = Path(f.name)

        try:
            files = pipeline.find_recent_pdfs(
                data_dir=temp_data_dir,
                num_files=3,
                output_file=output_file
            )

            # Check that output file was created
            assert output_file.exists()

            # Load and verify contents
            with Path(output_file).open() as f:
                saved_files = json.load(f)

            assert len(saved_files) == 3
            assert saved_files == files

        finally:
            if output_file.exists():
                output_file.unlink()

    def test_find_recent_pdfs_no_directory(self):
        """Test finding PDFs when directory doesn't exist."""
        pipeline = CompletePipeline()

        with pytest.raises(FileNotFoundError, match="Data directory not found"):
            pipeline.find_recent_pdfs(data_dir="/nonexistent/directory")

    def test_find_recent_pdfs_no_pdfs(self):
        """Test finding PDFs when no PDFs exist."""
        pipeline = CompletePipeline()

        with tempfile.TemporaryDirectory() as temp_dir:
            empty_dir = Path(temp_dir) / "empty"
            empty_dir.mkdir()

            with pytest.raises(FileNotFoundError, match="No PDF files found"):
                pipeline.find_recent_pdfs(data_dir=empty_dir)

    def test_run_pipeline_success(self, temp_db, temp_data_dir, mock_extractor, mock_embedder):
        """Test successful pipeline run."""
        with patch("rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor), \
             patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):

            pipeline = CompletePipeline(
                registry=temp_db,
                extractor_name="mock_extractor",
                embedder_name="mock_embedder",
                project_id="test_pipeline",
            )

            result = pipeline.run_pipeline(
                data_dir=temp_data_dir,
                num_files=2,
                test_mode=True,  # Will process only first 3 files
            )

            # Check pipeline success
            assert result["success"] is True
            assert result["duration_seconds"] > 0

            # Check steps
            assert "find_files" in result["steps"]
            assert result["steps"]["find_files"]["success"] is True
            assert result["steps"]["find_files"]["files_found"] == 2

            assert "process_documents" in result["steps"]
            assert result["steps"]["process_documents"]["success"] is True
            assert result["steps"]["process_documents"]["successful"] > 0

            assert "statistics" in result["steps"]
            assert result["steps"]["statistics"]["success"] is True

            # Check configuration
            config = result["pipeline_config"]
            assert config["project_id"] == "test_pipeline"
            assert config["extractor"] == "mock_extractor"
            assert config["embedder"] == "mock_embedder"
            assert config["test_mode"] is True

    def test_run_pipeline_no_files(self, temp_db):
        """Test pipeline run when no files are found."""
        with tempfile.TemporaryDirectory() as temp_dir:
            empty_dir = Path(temp_dir) / "empty"
            empty_dir.mkdir()

            pipeline = CompletePipeline(registry=temp_db)

            result = pipeline.run_pipeline(data_dir=empty_dir)

            assert result["success"] is False
            assert "find_files" in result["steps"]
            assert result["steps"]["find_files"]["success"] is False

    def test_validate_prerequisites_success(self, temp_data_dir, mock_extractor, mock_embedder):
        """Test successful prerequisites validation."""
        with patch("rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor), \
             patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):

            pipeline = CompletePipeline(
                extractor_name="mock_extractor",
                embedder_name="mock_embedder",
            )

            result = pipeline.validate_prerequisites(data_dir=temp_data_dir)

            assert result is True

    def test_validate_prerequisites_no_data_dir(self, mock_extractor, mock_embedder):
        """Test prerequisites validation with missing data directory."""
        with patch("rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor), \
             patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):

            pipeline = CompletePipeline(
                extractor_name="mock_extractor",
                embedder_name="mock_embedder",
            )

            result = pipeline.validate_prerequisites(data_dir="/nonexistent")

            assert result is False

    def test_validate_prerequisites_no_pdfs(self, mock_extractor, mock_embedder):
        """Test prerequisites validation with no PDFs."""
        with tempfile.TemporaryDirectory() as temp_dir, \
             patch("rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor), \
             patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):

            empty_dir = Path(temp_dir) / "empty"
            empty_dir.mkdir()

            pipeline = CompletePipeline(
                extractor_name="mock_extractor",
                embedder_name="mock_embedder",
            )

            result = pipeline.validate_prerequisites(data_dir=empty_dir)

            assert result is False

    def test_get_project_summary(self, temp_db, temp_data_dir, mock_extractor, mock_embedder):
        """Test getting project summary."""
        with patch("rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor), \
             patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder):

            pipeline = CompletePipeline(
                registry=temp_db,
                extractor_name="mock_extractor",
                embedder_name="mock_embedder",
                project_id="test_summary",
            )

            # Run pipeline first to create some data
            pipeline.run_pipeline(
                data_dir=temp_data_dir,
                num_files=1,
                test_mode=True,
            )

            # Get summary
            summary = pipeline.get_project_summary()

            assert "project_id" in summary
            assert summary["project_id"] == "test_summary"
            assert "total_documents" in summary
            assert "processing_stats" in summary
            assert "extractor" in summary
            assert "embedder" in summary
            assert summary["extractor"] == "mock_extractor"
            assert summary["embedder"] == "mock_embedder"

    def test_pipeline_with_log_file(self, temp_db, temp_data_dir, mock_extractor, mock_embedder):
        """Test pipeline with log file output."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            log_file = Path(f.name)

        try:
            with (
                patch(
                    "rkb.pipelines.ingestion_pipeline.get_extractor", return_value=mock_extractor
                ),
                patch("rkb.pipelines.ingestion_pipeline.get_embedder", return_value=mock_embedder),
            ):

                pipeline = CompletePipeline(
                    registry=temp_db,
                    extractor_name="mock_extractor",
                    embedder_name="mock_embedder",
                )

                result = pipeline.run_pipeline(
                    data_dir=temp_data_dir,
                    num_files=1,
                    test_mode=True,
                    log_file=log_file,
                )

                assert result["success"] is True

                # Check that log file was created and has content
                assert log_file.exists()

                with log_file.open() as f:
                    log_data = json.load(f)

                assert "pipeline_config" in log_data
                assert "results" in log_data
                assert len(log_data["results"]) > 0

        finally:
            if log_file.exists():
                log_file.unlink()
