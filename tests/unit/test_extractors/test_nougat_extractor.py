"""Tests for Nougat extractor."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rkb.core.models import ExtractionStatus
from rkb.extractors.nougat_extractor import NougatExtractor


class TestNougatExtractor:
    """Tests for NougatExtractor."""

    def test_extractor_initialization(self):
        """Test extractor initialization with default values."""
        extractor = NougatExtractor()

        assert extractor.chunk_size == 1
        assert extractor.max_pages == 50
        assert extractor.timeout_per_chunk == 120
        assert extractor.min_content_length == 50

    def test_extractor_initialization_with_params(self):
        """Test extractor initialization with custom parameters."""
        extractor = NougatExtractor(
            chunk_size=5,
            max_pages=100,
            timeout_per_chunk=180,
            min_content_length=100,
        )

        assert extractor.chunk_size == 5
        assert extractor.max_pages == 100
        assert extractor.timeout_per_chunk == 180
        assert extractor.min_content_length == 100

    def test_extract_nonexistent_file(self):
        """Test extracting from a nonexistent file."""
        extractor = NougatExtractor()
        result = extractor.extract(Path("/nonexistent/file.pdf"))

        assert result.status == ExtractionStatus.FAILED
        assert "File not found" in result.error_message

    def test_get_capabilities(self):
        """Test get_capabilities method."""
        extractor = NougatExtractor()
        capabilities = extractor.get_capabilities()

        assert capabilities["name"] == "nougat"
        assert capabilities["description"]
        assert ".pdf" in capabilities["supported_formats"]
        assert "mathematical_content" in capabilities["features"]
        assert "chunk_size" in capabilities["configuration"]

    @patch("subprocess.run")
    @patch("rkb.core.text_processing.hash_file")
    def test_extract_successful_processing(self, mock_hash, mock_subprocess):
        """Test successful PDF extraction."""
        # Setup mocks
        mock_hash.return_value = "test_hash"
        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stderr="",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create a mock PDF file
            pdf_file = temp_path / "test.pdf"
            pdf_file.write_bytes(b"mock pdf content")

            # Create mock nougat output
            def mock_nougat_side_effect(*args, **_kwargs):
                # Create the expected output file
                output_dir = Path(args[0][3])  # --out argument
                output_file = output_dir / "test.mmd"
                output_file.write_text(
                    "# Test Document\n\nSome extracted content with equations $E=mc^2$."
                )
                return MagicMock(returncode=0, stderr="")

            mock_subprocess.side_effect = mock_nougat_side_effect

            extractor = NougatExtractor(output_dir=temp_path / "output")
            result = extractor.extract(pdf_file)

            assert result.status == ExtractionStatus.COMPLETE
            assert result.extractor_name == "nougat"
            assert result.extractor_version == "1.0.0"
            assert len(result.chunks) > 0
            assert len(result.chunk_metadata) > 0
            assert result.extraction_path is not None
            assert result.content is not None

    def test_analyze_chunk_error(self):
        """Test chunk error analysis."""
        extractor = NougatExtractor()

        # Test known error patterns
        error_msg = extractor._analyze_chunk_error("Failed to load page 5", 1, 3)
        assert "Corrupted page" in error_msg
        assert "pages 1-3" in error_msg

        error_msg = extractor._analyze_chunk_error("list index out of range", 4, 6)
        assert "Dataloader error" in error_msg

        # Test unknown error
        error_msg = extractor._analyze_chunk_error("some unknown error", 7, 9)
        assert "Unknown error" in error_msg

        # Test empty stderr
        error_msg = extractor._analyze_chunk_error("", 10, 12)
        assert "No error output" in error_msg

    def test_create_extraction_header(self):
        """Test extraction header creation."""
        extractor = NougatExtractor()

        successful_chunks = [(1, 3), (4, 6)]
        failed_chunks = [(7, 9, "timeout")]

        header = extractor._create_extraction_header(
            Path("test.pdf"),
            "test_extraction_123",
            successful_chunks,
            failed_chunks,
        )

        assert "test.pdf" in header
        assert "test_extraction_123" in header
        assert "Successful chunks: 2" in header
        assert "Failed chunks: 1" in header

    @patch("subprocess.run")
    def test_extract_chunk_timeout(self, mock_subprocess):
        """Test chunk extraction timeout handling."""
        from subprocess import TimeoutExpired

        mock_subprocess.side_effect = TimeoutExpired("nougat", 120)

        extractor = NougatExtractor()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            pdf_file = temp_path / "test.pdf"
            pdf_file.write_bytes(b"mock pdf content")

            with pytest.raises(TimeoutExpired):
                extractor._extract_chunk(pdf_file, 1, 3, temp_path)

    @patch("subprocess.run")
    def test_extract_chunk_failure(self, mock_subprocess):
        """Test chunk extraction failure handling."""
        mock_subprocess.return_value = MagicMock(
            returncode=1,
            stderr="Failed to load page",
        )

        extractor = NougatExtractor()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            pdf_file = temp_path / "test.pdf"
            pdf_file.write_bytes(b"mock pdf content")

            with pytest.raises(RuntimeError, match="Corrupted page"):
                extractor._extract_chunk(pdf_file, 1, 3, temp_path)
