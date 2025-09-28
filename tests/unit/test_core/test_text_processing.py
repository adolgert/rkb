"""Tests for text processing utilities."""

import tempfile
from pathlib import Path

import pytest

from rkb.core.models import ChunkMetadata
from rkb.core.text_processing import (
    chunk_text_by_pages,
    clean_extracted_text,
    create_chunk_metadata,
    extract_arxiv_id,
    extract_doi,
    extract_equations,
    hash_file,
)


class TestExtractEquations:
    """Tests for equation extraction."""

    def test_extract_display_equations(self):
        """Test extracting display equations."""
        text = r"Here is a display equation: \[E = mc^2\] and more text."
        result = extract_equations(text)

        assert result["has_equations"] is True
        assert len(result["display_equations"]) == 1
        assert result["display_equations"][0] == "E = mc^2"
        assert len(result["inline_equations"]) == 0

    def test_extract_inline_equations(self):
        """Test extracting inline equations."""
        text = r"The formula $\alpha + \beta = \gamma$ is important."
        result = extract_equations(text)

        assert result["has_equations"] is True
        assert len(result["inline_equations"]) == 1
        assert result["inline_equations"][0] == r"\alpha + \beta = \gamma"
        assert len(result["display_equations"]) == 0

    def test_extract_mixed_equations(self):
        """Test extracting both types of equations."""
        text = r"""
        Consider the equation $f(x) = ax + b$ and the display form:
        \[\int_a^b f(x) dx = \frac{1}{2}(b^2 - a^2)\]
        """
        result = extract_equations(text)

        assert result["has_equations"] is True
        assert len(result["inline_equations"]) == 1
        assert len(result["display_equations"]) == 1

    def test_no_equations(self):
        """Test text without equations."""
        text = "This is just regular text without any mathematical content."
        result = extract_equations(text)

        assert result["has_equations"] is False
        assert len(result["inline_equations"]) == 0
        assert len(result["display_equations"]) == 0


class TestChunkTextByPages:
    """Tests for text chunking."""

    def test_chunk_small_text(self):
        """Test chunking text smaller than max size."""
        text = "This is a small text that should not be chunked."
        chunks = chunk_text_by_pages(text, max_chunk_size=1000)

        assert len(chunks) == 1
        assert chunks[0] == text

    def test_chunk_large_text(self):
        """Test chunking text larger than max size."""
        paragraphs = ["This is paragraph one."] * 50
        text = "\n\n".join(paragraphs)
        chunks = chunk_text_by_pages(text, max_chunk_size=200)

        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 250  # Allow some flexibility

    def test_chunk_empty_text(self):
        """Test chunking empty text."""
        chunks = chunk_text_by_pages("", max_chunk_size=1000)

        assert len(chunks) == 0

    def test_chunk_preserves_paragraphs(self):
        """Test that paragraph boundaries are preserved."""
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        chunks = chunk_text_by_pages(text, max_chunk_size=1000)

        assert len(chunks) == 1
        assert "\n\n" in chunks[0]


class TestCreateChunkMetadata:
    """Tests for chunk metadata creation."""

    def test_create_metadata_for_chunks(self):
        """Test creating metadata for text chunks."""
        chunks = [
            "Regular text without equations.",
            r"Text with inline equation $E = mc^2$ here.",
            r"Text with display equation: \[\int f(x) dx\] and more.",
        ]

        metadata_list = create_chunk_metadata(chunks)

        assert len(metadata_list) == 3
        assert all(isinstance(m, ChunkMetadata) for m in metadata_list)

        # Check first chunk (no equations)
        assert metadata_list[0].chunk_index == 0
        assert metadata_list[0].has_equations is False
        assert metadata_list[0].display_eq_count == 0
        assert metadata_list[0].inline_eq_count == 0

        # Check second chunk (inline equation)
        assert metadata_list[1].chunk_index == 1
        assert metadata_list[1].has_equations is True
        assert metadata_list[1].inline_eq_count == 1

        # Check third chunk (display equation)
        assert metadata_list[2].chunk_index == 2
        assert metadata_list[2].has_equations is True
        assert metadata_list[2].display_eq_count == 1

    def test_create_metadata_with_offset(self):
        """Test creating metadata with index offset."""
        chunks = ["First chunk", "Second chunk"]
        metadata_list = create_chunk_metadata(chunks, chunk_index_offset=10)

        assert metadata_list[0].chunk_index == 10
        assert metadata_list[1].chunk_index == 11


class TestHashFile:
    """Tests for file hashing."""

    def test_hash_existing_file(self):
        """Test hashing an existing file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("Test content for hashing")
            temp_path = Path(f.name)

        try:
            hash_result = hash_file(temp_path)
            assert isinstance(hash_result, str)
            assert len(hash_result) == 32  # MD5 hash length
        finally:
            temp_path.unlink()

    def test_hash_nonexistent_file(self):
        """Test hashing a nonexistent file."""
        with pytest.raises(FileNotFoundError):
            hash_file(Path("/nonexistent/file.txt"))

    def test_hash_consistency(self):
        """Test that same content produces same hash."""
        content = "Consistent content for testing"

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f1:
            f1.write(content)
            temp_path1 = Path(f1.name)

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f2:
            f2.write(content)
            temp_path2 = Path(f2.name)

        try:
            hash1 = hash_file(temp_path1)
            hash2 = hash_file(temp_path2)
            assert hash1 == hash2
        finally:
            temp_path1.unlink()
            temp_path2.unlink()


class TestExtractArxivId:
    """Tests for ArXiv ID extraction."""

    def test_extract_arxiv_id_with_version(self):
        """Test extracting ArXiv ID with version."""
        filename = "2506.06542v1.pdf"
        arxiv_id = extract_arxiv_id(filename)

        assert arxiv_id == "2506.06542v1"

    def test_extract_arxiv_id_without_version(self):
        """Test extracting ArXiv ID without version."""
        filename = "1501.03291.pdf"
        arxiv_id = extract_arxiv_id(filename)

        assert arxiv_id == "1501.03291"

    def test_extract_arxiv_id_in_path(self):
        """Test extracting ArXiv ID from full path."""
        filename = "/downloads/papers/2410.15474v1_paper.pdf"
        arxiv_id = extract_arxiv_id(filename)

        assert arxiv_id == "2410.15474v1"

    def test_extract_arxiv_id_none(self):
        """Test extracting ArXiv ID from non-ArXiv filename."""
        filename = "regular_paper.pdf"
        arxiv_id = extract_arxiv_id(filename)

        assert arxiv_id is None


class TestExtractDoi:
    """Tests for DOI extraction."""

    def test_extract_doi_with_prefix(self):
        """Test extracting DOI with DOI prefix."""
        text = "The paper is published at DOI: 10.1000/test.doi.12345"
        doi = extract_doi(text)

        assert doi == "10.1000/test.doi.12345"

    def test_extract_doi_without_prefix(self):
        """Test extracting DOI without prefix."""
        text = "Available at 10.1038/nature12345 for reference."
        doi = extract_doi(text)

        assert doi == "10.1038/nature12345"

    def test_extract_doi_none(self):
        """Test text without DOI."""
        text = "This text contains no DOI information."
        doi = extract_doi(text)

        assert doi is None


class TestCleanExtractedText:
    """Tests for text cleaning."""

    def test_clean_excessive_whitespace(self):
        """Test removing excessive whitespace."""
        text = "Line one\n\n\n\nLine two with  multiple   spaces"
        cleaned = clean_extracted_text(text)

        assert "\n\n\n" not in cleaned
        assert "  " not in cleaned
        assert cleaned == "Line one\n\nLine two with multiple spaces"

    def test_clean_normalize_quotes(self):
        """Test normalizing quote characters."""
        text = "This has \"smart quotes\" and 'apostrophes' to normalize."
        cleaned = clean_extracted_text(text)

        assert '"smart quotes"' in cleaned
        assert "'apostrophes'" in cleaned

    def test_clean_empty_text(self):
        """Test cleaning empty text."""
        cleaned = clean_extracted_text("")

        assert cleaned == ""

    def test_clean_whitespace_only(self):
        """Test cleaning whitespace-only text."""
        text = "   \n\n   \n  "
        cleaned = clean_extracted_text(text)

        assert cleaned == ""
