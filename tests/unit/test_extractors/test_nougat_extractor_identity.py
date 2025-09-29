"""Tests for NougatExtractor doc_id and path functionality."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from rkb.core.models import ExtractionStatus
from rkb.extractors.nougat_extractor import NougatExtractor


class TestNougatExtractorIdentity:
    """Test NougatExtractor doc_id functionality."""

    @pytest.fixture
    def temp_extractor(self):
        """Create extractor with temporary output directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            extractor = NougatExtractor(output_dir=Path(temp_dir))
            yield extractor

    @pytest.fixture
    def sample_pdf(self):
        """Create a sample PDF file."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"Mock PDF content")
            f.flush()
            pdf_path = Path(f.name)
            yield pdf_path
            pdf_path.unlink()

    def test_extract_with_provided_doc_id(self, temp_extractor, sample_pdf):
        """Test extraction with provided doc_id."""
        doc_id = "test-doc-id-123"

        with patch.object(temp_extractor, "_extract_pdf_chunks") as mock_extract:
            mock_extract.return_value = {
                "content": "Extracted content",
                "successful_chunks": [(1, 3)],
                "failed_chunks": [],
                "total_pages_processed": 3
            }

            result = temp_extractor.extract(sample_pdf, doc_id=doc_id)

            assert result.doc_id == doc_id
            assert result.status == ExtractionStatus.COMPLETE
            assert doc_id in str(result.extraction_path)
            assert "documents" in str(result.extraction_path)

    def test_extract_generates_doc_id_when_not_provided(self, temp_extractor, sample_pdf):
        """Test that doc_id is generated when not provided."""
        with patch.object(temp_extractor, "_extract_pdf_chunks") as mock_extract:
            mock_extract.return_value = {
                "content": "Extracted content",
                "successful_chunks": [(1, 3)],
                "failed_chunks": [],
                "total_pages_processed": 3
            }

            result = temp_extractor.extract(sample_pdf)

            assert result.doc_id is not None
            assert len(result.doc_id) == 36  # UUID length
            assert result.status == ExtractionStatus.COMPLETE

    def test_extract_creates_doc_id_directory_structure(self, temp_extractor, sample_pdf):
        """Test that extraction creates proper directory structure."""
        doc_id = "test-doc-id-456"

        with patch.object(temp_extractor, "_extract_pdf_chunks") as mock_extract:
            mock_extract.return_value = {
                "content": "Extracted content",
                "successful_chunks": [(1, 3)],
                "failed_chunks": [],
                "total_pages_processed": 3
            }

            result = temp_extractor.extract(sample_pdf, doc_id=doc_id)

            # Check that the directory structure exists
            expected_dir = temp_extractor.output_dir / "documents" / doc_id
            assert expected_dir.exists()
            assert expected_dir.is_dir()

            # Check that the extraction file exists
            expected_file = expected_dir / "extracted.mmd"
            assert expected_file.exists()
            assert expected_file == result.extraction_path

    def test_extract_file_not_found_with_doc_id(self, temp_extractor):
        """Test extraction failure when file doesn't exist."""
        doc_id = "test-doc-id-404"
        nonexistent_file = Path("/nonexistent/file.pdf")

        result = temp_extractor.extract(nonexistent_file, doc_id=doc_id)

        assert result.doc_id == doc_id
        assert result.status == ExtractionStatus.FAILED
        assert "File not found" in result.error_message

    def test_extract_no_content_extracted_with_doc_id(self, temp_extractor, sample_pdf):
        """Test extraction when no content is extracted."""
        doc_id = "test-doc-id-empty"

        with patch.object(temp_extractor, "_extract_pdf_chunks") as mock_extract:
            mock_extract.return_value = {
                "content": "",
                "successful_chunks": [],
                "failed_chunks": [(1, 3, "error")],
                "total_pages_processed": 0
            }

            result = temp_extractor.extract(sample_pdf, doc_id=doc_id)

            assert result.doc_id == doc_id
            assert result.status == ExtractionStatus.FAILED
            assert "No content extracted" in result.error_message

    def test_extract_exception_handling_with_doc_id(self, temp_extractor, sample_pdf):
        """Test exception handling during extraction."""
        doc_id = "test-doc-id-error"

        with patch.object(temp_extractor, "_extract_pdf_chunks") as mock_extract:
            mock_extract.side_effect = Exception("Extraction failed")

            result = temp_extractor.extract(sample_pdf, doc_id=doc_id)

            assert result.doc_id == doc_id
            assert result.status == ExtractionStatus.FAILED
            assert "Extraction failed" in result.error_message

    def test_extraction_id_includes_doc_id(self, temp_extractor, sample_pdf):
        """Test that extraction_id includes doc_id."""
        doc_id = "test-doc-id-789"

        with patch.object(temp_extractor, "_extract_pdf_chunks") as mock_extract:
            mock_extract.return_value = {
                "content": "Extracted content",
                "successful_chunks": [(1, 3)],
                "failed_chunks": [],
                "total_pages_processed": 3
            }

            result = temp_extractor.extract(sample_pdf, doc_id=doc_id)

            assert doc_id in result.extraction_id
            assert result.extraction_id.startswith(doc_id)

    def test_extraction_path_uses_pathresolver(self, temp_extractor, sample_pdf):
        """Test that extraction path follows PathResolver pattern."""
        doc_id = "test-doc-id-pathresolver"

        with patch.object(temp_extractor, "_extract_pdf_chunks") as mock_extract:
            mock_extract.return_value = {
                "content": "Extracted content",
                "successful_chunks": [(1, 3)],
                "failed_chunks": [],
                "total_pages_processed": 3
            }

            result = temp_extractor.extract(sample_pdf, doc_id=doc_id)

            # Verify path structure follows PathResolver pattern
            expected_pattern = f"documents/{doc_id}/extracted.mmd"
            assert expected_pattern in str(result.extraction_path)
            assert result.extraction_path.suffix == ".mmd"
