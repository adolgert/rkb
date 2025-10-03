"""Tests for FilenameExtractor."""

from pathlib import Path

from rkb.extractors.metadata.filename_extractor import FilenameExtractor


def test_filename_extractor_name():
    """Test extractor name."""
    extractor = FilenameExtractor()
    assert extractor.name == "filename"


def test_filename_extractor_arxiv_pattern():
    """Test arXiv filename pattern extraction."""
    extractor = FilenameExtractor()
    pdf_path = Path("/tmp/2301.12345v1.pdf")

    metadata = extractor.extract(pdf_path)

    # arXiv pattern extracts year from the ID prefix (2301 -> 2023 era, but too high)
    # The year extraction only accepts 19xx or 20xx, so 2301 is not valid
    assert metadata.year is None  # 2301 is out of valid range
    assert metadata.extractor == "filename"


def test_filename_extractor_author_year():
    """Test author-year pattern extraction."""
    extractor = FilenameExtractor()
    pdf_path = Path("/tmp/Smith2023_MachineLearning.pdf")

    metadata = extractor.extract(pdf_path)

    assert metadata.authors == ["Smith"]
    assert metadata.year == 2023
    assert metadata.extractor == "filename"


def test_filename_extractor_year_only():
    """Test year-only extraction."""
    extractor = FilenameExtractor()
    pdf_path = Path("/tmp/paper_2023.pdf")

    metadata = extractor.extract(pdf_path)

    assert metadata.year == 2023
    assert metadata.authors is None


def test_filename_extractor_no_patterns():
    """Test filename with no recognizable patterns."""
    extractor = FilenameExtractor()
    pdf_path = Path("/tmp/document.pdf")

    metadata = extractor.extract(pdf_path)

    assert metadata.year is None
    assert metadata.authors is None
    assert metadata.title is None
    assert metadata.extractor == "filename"


def test_filename_extractor_author_no_year():
    """Test author without year."""
    extractor = FilenameExtractor()
    pdf_path = Path("/tmp/Johnson_paper.pdf")

    metadata = extractor.extract(pdf_path)

    assert metadata.authors == ["Johnson"]
    assert metadata.year is None
