"""Text processing utilities for the RKB system."""

import hashlib
import re
from pathlib import Path

from rkb.core.models import ChunkMetadata


def extract_equations(text: str) -> dict[str, any]:
    """Extract LaTeX equations from text.

    Args:
        text: Text content to analyze

    Returns:
        Dictionary containing:
        - display_equations: list of display equations
        - inline_equations: list of inline equations
        - has_equations: bool indicating presence of equations
    """
    # Pattern for display equations \[...\] and inline equations $...$
    display_equations = re.findall(r"\\\[(.*?)\\\]", text, re.DOTALL)
    inline_equations = re.findall(r"\$(.*?)\$", text)

    return {
        "display_equations": display_equations,
        "inline_equations": inline_equations,
        "has_equations": len(display_equations) + len(inline_equations) > 0,
    }


def chunk_text_by_pages(content: str, max_chunk_size: int = 2000) -> list[tuple[str, list[int]]]:
    """Split markdown content into page-based chunks with page tracking.

    Extracts page numbers from Nougat's <!-- Pages X-Y --> markers and tracks
    which pages each chunk spans.

    Args:
        content: Text content to chunk (from Nougat extraction)
        max_chunk_size: Maximum size per chunk in characters

    Returns:
        List of (chunk_text, page_numbers) tuples
    """
    # Extract page boundaries from Nougat markers
    page_markers = []
    for match in re.finditer(r"<!-- Pages (\d+)-(\d+) -->", content):
        start_page = int(match.group(1))
        end_page = int(match.group(2))
        marker_pos = match.start()
        page_markers.append((marker_pos, start_page, end_page))

    # Build character position to page number mapping
    def get_page_at_position(pos: int) -> int:
        """Get page number at given character position."""
        for i, (marker_pos, start_page, end_page) in enumerate(page_markers):
            # Find which page range this position falls into
            next_marker_pos = page_markers[i + 1][0] if i + 1 < len(page_markers) else len(content)
            if marker_pos <= pos < next_marker_pos:
                # Estimate page within range based on position
                if end_page == start_page:
                    return start_page
                range_size = next_marker_pos - marker_pos
                offset = pos - marker_pos
                page_offset = int((end_page - start_page + 1) * (offset / range_size))
                return min(start_page + page_offset, end_page)
        return 1  # Default to page 1 if no markers found

    # Split by paragraphs
    paragraphs = content.split("\n\n")

    chunks = []
    current_chunk = ""
    current_start_pos = 0

    for paragraph in paragraphs:
        # If adding this paragraph would exceed max size, save current chunk
        if len(current_chunk) + len(paragraph) > max_chunk_size and current_chunk:
            # Calculate page numbers for this chunk
            chunk_pages = set()
            if page_markers:
                # Sample positions throughout the chunk
                chunk_len = len(current_chunk)
                sample_positions = [
                    current_start_pos + int(chunk_len * i / 10)
                    for i in range(11)
                ]
                for pos in sample_positions:
                    chunk_pages.add(get_page_at_position(pos))
            else:
                chunk_pages.add(1)

            chunks.append((current_chunk.strip(), sorted(chunk_pages)))
            current_start_pos += len(current_chunk) + 2  # +2 for "\n\n"
            current_chunk = paragraph
        elif current_chunk:
            current_chunk += "\n\n" + paragraph
        else:
            current_chunk = paragraph

    # Add the last chunk
    if current_chunk.strip():
        chunk_pages = set()
        if page_markers:
            chunk_len = len(current_chunk)
            sample_positions = [
                current_start_pos + int(chunk_len * i / 10)
                for i in range(11)
            ]
            for pos in sample_positions:
                chunk_pages.add(get_page_at_position(pos))
        else:
            chunk_pages.add(1)

        chunks.append((current_chunk.strip(), sorted(chunk_pages)))

    return chunks


def create_chunk_metadata(
    chunks: list[tuple[str, list[int]]],
    chunk_index_offset: int = 0
) -> list[ChunkMetadata]:
    """Create metadata for text chunks with page numbers.

    Args:
        chunks: List of (chunk_text, page_numbers) tuples
        chunk_index_offset: Starting index for chunk numbering

    Returns:
        List of ChunkMetadata objects
    """
    metadata_list = []

    for i, (chunk, page_numbers) in enumerate(chunks):
        equation_info = extract_equations(chunk)
        metadata = ChunkMetadata(
            chunk_index=i + chunk_index_offset,
            chunk_length=len(chunk),
            has_equations=equation_info["has_equations"],
            display_eq_count=len(equation_info["display_equations"]),
            inline_eq_count=len(equation_info["inline_equations"]),
            page_numbers=page_numbers,
        )
        metadata_list.append(metadata)

    return metadata_list


def hash_file(file_path: Path) -> str:
    """Calculate MD5 hash of a file for duplicate detection.

    Args:
        file_path: Path to the file

    Returns:
        MD5 hash as hexadecimal string

    Raises:
        FileNotFoundError: If file doesn't exist
        IOError: If file cannot be read
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    md5_hash = hashlib.md5()
    try:
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()
    except OSError as e:
        raise OSError(f"Cannot read file {file_path}: {e}") from e


def extract_arxiv_id(filename: str) -> str | None:
    """Extract ArXiv ID from filename.

    Args:
        filename: Name of the file

    Returns:
        ArXiv ID if found, None otherwise

    Examples:
        >>> extract_arxiv_id("2506.06542v1.pdf")
        "2506.06542v1"
        >>> extract_arxiv_id("1501.03291v3.pdf")
        "1501.03291v3"
    """
    # Pattern for ArXiv IDs: YYMM.NNNNN[vN]
    arxiv_pattern = r"(\d{4}\.\d{4,5}(?:v\d+)?)"
    match = re.search(arxiv_pattern, filename)
    return match.group(1) if match else None


def extract_doi(text: str) -> str | None:
    """Extract DOI from text content.

    Args:
        text: Text content to search

    Returns:
        DOI if found, None otherwise
    """
    # Pattern for DOIs
    doi_pattern = r"(?:doi:|DOI:)?\s*(10\.\d+/[^\s]+)"
    match = re.search(doi_pattern, text, re.IGNORECASE)
    return match.group(1) if match else None


def clean_extracted_text(text: str) -> str:
    """Clean extracted text by removing common OCR artifacts.

    Args:
        text: Raw extracted text

    Returns:
        Cleaned text
    """
    # Remove excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)

    # Remove page numbers at end of lines
    text = re.sub(r"\n\d+\s*$", "", text, flags=re.MULTILINE)

    # Clean up common OCR artifacts
    text = re.sub(r"[\u201c\u201d]", '"', text)  # Normalize quotes
    text = re.sub(r"[\u2018\u2019]", "'", text)  # Normalize apostrophes

    return text.strip()
