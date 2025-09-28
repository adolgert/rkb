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


def chunk_text_by_pages(content: str, max_chunk_size: int = 2000) -> list[str]:
    """Split markdown content into page-based chunks.

    Args:
        content: Text content to chunk
        max_chunk_size: Maximum size per chunk in characters

    Returns:
        List of text chunks
    """
    # Split by pages if we can identify page boundaries
    # For now, use simple paragraph-based chunking
    paragraphs = content.split("\n\n")

    chunks = []
    current_chunk = ""

    for paragraph in paragraphs:
        # If adding this paragraph would exceed max size, save current chunk
        if len(current_chunk) + len(paragraph) > max_chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            current_chunk = paragraph
        elif current_chunk:
            current_chunk += "\n\n" + paragraph
        else:
            current_chunk = paragraph

    # Add the last chunk
    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def create_chunk_metadata(chunks: list[str], chunk_index_offset: int = 0) -> list[ChunkMetadata]:
    """Create metadata for text chunks.

    Args:
        chunks: List of text chunks
        chunk_index_offset: Starting index for chunk numbering

    Returns:
        List of ChunkMetadata objects
    """
    metadata_list = []

    for i, chunk in enumerate(chunks):
        equation_info = extract_equations(chunk)
        metadata = ChunkMetadata(
            chunk_index=i + chunk_index_offset,
            chunk_length=len(chunk),
            has_equations=equation_info["has_equations"],
            display_eq_count=len(equation_info["display_equations"]),
            inline_eq_count=len(equation_info["inline_equations"]),
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
