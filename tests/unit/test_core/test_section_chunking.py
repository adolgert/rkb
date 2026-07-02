"""Tests for section-aware chunking in text_processing."""

from rkb.core.text_processing import chunk_text_by_sections


def test_h1_sections_split_correctly() -> None:
    """Doc with H1 sections produces one chunk per section."""
    content = """\
# Introduction

This is the introduction text.

# Methods

This is the methods section.

# Results

This is the results section.
"""
    chunks = chunk_text_by_sections(content, min_chunk_size=0)
    assert len(chunks) == 3
    texts = [t for t, _ in chunks]
    hierarchies = [h for _, h in chunks]
    assert any("Introduction" in t for t in texts)
    assert any("Methods" in t for t in texts)
    assert any("Results" in t for t in texts)
    # Every hierarchy entry should name the heading
    assert ["Introduction"] in hierarchies
    assert ["Methods"] in hierarchies
    assert ["Results"] in hierarchies


def test_h2_top_level_when_no_h1() -> None:
    """Doc with only H2 headings uses H2 as the delimiter."""
    content = """\
## Background

Some background text.

## Approach

Our approach details.
"""
    chunks = chunk_text_by_sections(content, min_chunk_size=0)
    assert len(chunks) == 2
    _, h0 = chunks[0]
    _, h1 = chunks[1]
    assert h0 == ["Background"]
    assert h1 == ["Approach"]


def test_long_section_is_sub_chunked_with_heading_prepended() -> None:
    """A section that exceeds max_chunk_size is split; heading prepended."""
    para = "Word " * 100  # ~500 chars per paragraph
    content = "# Long Section\n\n" + "\n\n".join([para] * 10)
    # 10 * ~500 = ~5000 chars, clearly exceeds default 3000
    chunks = chunk_text_by_sections(content, max_chunk_size=1500)
    # Should have produced multiple sub-chunks
    assert len(chunks) > 1
    # Every sub-chunk text should reference the heading
    for text, hierarchy in chunks:
        assert hierarchy == ["Long Section"]
        assert "Long Section" in text


def test_no_headings_falls_back_to_page_chunking() -> None:
    """Doc with no headings falls back to page-based chunking (empty hierarchy)."""
    content = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
    chunks = chunk_text_by_sections(content)
    assert len(chunks) >= 1
    # All hierarchies should be empty since there are no headings
    for _, hierarchy in chunks:
        assert hierarchy == []


def test_bold_wrapped_headings_are_stripped() -> None:
    """Bold markers around heading text are removed."""
    content = """\
## **Introduction**

Some text here.

## __Methods__

More text.
"""
    chunks = chunk_text_by_sections(content, min_chunk_size=0)
    hierarchies = [h for _, h in chunks]
    assert ["Introduction"] in hierarchies
    assert ["Methods"] in hierarchies
    # Raw bold markers should not appear in hierarchy
    for h in hierarchies:
        for name in h:
            assert "**" not in name
            assert "__" not in name
