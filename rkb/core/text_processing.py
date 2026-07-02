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


def _merge_small_chunks(
    chunks: list[tuple[str, list[str]]], min_chunk_size: int
) -> list[tuple[str, list[str]]]:
    """Merge chunks below min_chunk_size forward into the next chunk.

    A chunk that is too small is prepended to the following chunk, separated
    by a blank line.  The merged chunk inherits the *next* chunk's section
    hierarchy (since the content continues there).  If the last chunk is too
    small it is merged backward into the preceding chunk instead.
    """
    if not chunks or min_chunk_size <= 0:
        return chunks

    merged: list[tuple[str, list[str]]] = []
    pending_text = ""
    pending_hierarchy: list[str] = []

    for chunk_text, hierarchy in chunks:
        text = chunk_text
        if pending_text:
            # Prepend the pending small chunk to this one
            text = pending_text + "\n\n" + text
            pending_text = ""
            pending_hierarchy = []

        if len(text) < min_chunk_size:
            # Hold this chunk and try to merge it with the next one
            pending_text = text
            pending_hierarchy = hierarchy
        else:
            merged.append((text, hierarchy))

    # Handle leftover: merge backward into the last kept chunk
    if pending_text:
        if merged:
            last_text, last_hierarchy = merged[-1]
            merged[-1] = (last_text + "\n\n" + pending_text, last_hierarchy)
        else:
            merged.append((pending_text, pending_hierarchy))

    return merged


def chunk_text_by_sections(
    content: str, max_chunk_size: int = 3000, min_chunk_size: int = 200
) -> list[tuple[str, list[str]]]:
    """Split markdown content into section-based chunks with section hierarchy.

    Finds the minimum heading level present in the document and splits at that
    level. Falls back to chunk_text_by_pages if no headings are found.

    Strips bold wrappers from heading text (e.g. ``## **Introduction**``
    becomes ``Introduction``).

    Chunks smaller than min_chunk_size are merged forward into the next chunk
    so that section-header-only chunks do not become standalone embeddings.

    Args:
        content: Text content to chunk (markdown format)
        max_chunk_size: Maximum size per chunk in characters
        min_chunk_size: Chunks shorter than this are merged into the next chunk

    Returns:
        List of (chunk_text, section_hierarchy) tuples where section_hierarchy
        is a list of heading strings for the section (currently always one
        element — the immediate heading).  Falls back to
        chunk_text_by_pages with empty section_hierarchy if no headings found.
    """
    heading_re = re.compile(r"^(#{1,6}) +(.+)$", re.MULTILINE)
    all_headings = heading_re.findall(content)

    if not all_headings:
        # Fall back to page-based chunking with empty section hierarchy
        page_chunks = chunk_text_by_pages(content, max_chunk_size)
        return [(text, []) for text, _ in page_chunks]

    # Find minimum heading level present
    min_level = min(len(hashes) for hashes, _ in all_headings)
    top_re = re.compile(r"^#{" + str(min_level) + r"}(?!#) +(.+)$", re.MULTILINE)

    def _strip_bold(text: str) -> str:
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"__(.+?)__", r"\1", text)
        return text.strip()

    # Locate all top-level heading positions
    splits = list(top_re.finditer(content))

    chunks: list[tuple[str, list[str]]] = []

    def _add_section(body: str, heading: str) -> None:
        """Add a section body; sub-chunk if it exceeds max_chunk_size."""
        heading_line = "#" * min_level + " " + heading
        if len(body) <= max_chunk_size:
            chunks.append((body, [heading]))
            return
        # Sub-chunk by paragraphs; prepend heading to every sub-chunk
        paragraphs = re.split(r"\n\n+", body)
        current = ""
        for para in paragraphs:
            candidate = current + ("\n\n" if current else "") + para
            if current and len(heading_line + "\n\n" + candidate) > max_chunk_size:
                chunks.append((heading_line + "\n\n" + current.strip(), [heading]))
                current = para
            else:
                current = candidate
        if current.strip():
            chunks.append((heading_line + "\n\n" + current.strip(), [heading]))

    # Content before the first top-level heading
    if splits:
        preamble = content[: splits[0].start()].strip()
        if preamble:
            if len(preamble) <= max_chunk_size:
                chunks.append((preamble, []))
            else:
                page_chunks = chunk_text_by_pages(preamble, max_chunk_size)
                chunks.extend((text, []) for text, _ in page_chunks)

    # Process each top-level section
    for i, match in enumerate(splits):
        raw_heading = match.group(1)
        heading_text = _strip_bold(raw_heading)

        # Section body spans from the matched heading line to the next split
        sec_start = match.start()
        sec_end = splits[i + 1].start() if i + 1 < len(splits) else len(content)
        section_body = content[sec_start:sec_end].strip()

        _add_section(section_body, heading_text)

    if not chunks:
        return [(content, [])]

    return _merge_small_chunks(chunks, min_chunk_size)


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
