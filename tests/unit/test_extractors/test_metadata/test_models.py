"""Tests for DocumentMetadata model."""

from rkb.extractors.metadata.models import DocumentMetadata


def test_document_metadata_defaults():
    """Test DocumentMetadata with default values."""
    metadata = DocumentMetadata()

    assert metadata.doc_type is None
    assert metadata.title is None
    assert metadata.authors is None
    assert metadata.year is None
    assert metadata.journal is None
    assert metadata.page_count is None
    assert metadata.extractor == ""


def test_document_metadata_format_line1():
    """Test line 1 formatting."""
    metadata = DocumentMetadata(
        authors=["Smith", "Jones"], title="Test Paper", extractor="test"
    )

    assert metadata.format_line1() == 'Smith, "Test Paper"'


def test_document_metadata_format_line1_unknown():
    """Test line 1 formatting with missing data."""
    metadata = DocumentMetadata(extractor="test")

    assert metadata.format_line1() == "unknown, unknown"


def test_document_metadata_format_line2():
    """Test line 2 formatting."""
    metadata = DocumentMetadata(
        year=2023,
        doc_type="article",
        journal="Nature",
        page_count=10,
        extractor="test",
    )

    assert metadata.format_line2() == "2023, article, Nature, 10"


def test_document_metadata_format_line2_partial():
    """Test line 2 formatting with partial data."""
    metadata = DocumentMetadata(year=2023, page_count=10, extractor="test")

    assert metadata.format_line2() == "2023, unknown, unknown, 10"


def test_document_metadata_format_line2_unknown():
    """Test line 2 formatting with missing data."""
    metadata = DocumentMetadata(extractor="test")

    assert metadata.format_line2() == "unknown, unknown, unknown, unknown"
