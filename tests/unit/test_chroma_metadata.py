"""Unit test to reproduce and fix ChromaDB metadata issue."""



def test_chroma_metadata_with_list_fails():
    """Verify that ChromaDB rejects list values in metadata."""
    import tempfile
    from pathlib import Path

    from rkb.embedders.chroma_embedder import ChromaEmbedder

    with tempfile.TemporaryDirectory() as tmpdir:
        embedder = ChromaEmbedder(db_path=Path(tmpdir) / "test_chroma")

        # This is what ingestion_pipeline.py currently does - passes a list for page_numbers
        metadata_with_list = {
            "doc_id": "test_doc",
            "chunk_index": 0,
            "page_numbers": [1],  # This is a list - ChromaDB will reject it
            "has_equations": False,
            "display_eq_count": 0,
            "inline_eq_count": 0,
        }

        chunks = ["This is a test chunk of text."]
        metadatas = [metadata_with_list]

        result = embedder.embed(chunks, metadatas)

        # Currently this fails with error about list not being allowed

        # The error should mention list not being allowed
        assert result.error_message is not None, "Expected an error but got none"
        assert "list" in result.error_message.lower(), f"Unexpected error: {result.error_message}"
        assert result.chunk_count == 0, "No chunks should be embedded when metadata is invalid"


def test_chroma_metadata_with_string_works():
    """Verify that ChromaDB accepts string values in metadata."""
    import tempfile
    from pathlib import Path

    from rkb.embedders.chroma_embedder import ChromaEmbedder

    with tempfile.TemporaryDirectory() as tmpdir:
        embedder = ChromaEmbedder(db_path=Path(tmpdir) / "test_chroma")

        # Fix: Convert list to string (e.g., "1" or "1,2,3")
        metadata_with_string = {
            "doc_id": "test_doc",
            "chunk_index": 0,
            "page_numbers": "1",  # String instead of list
            "has_equations": False,
            "display_eq_count": 0,
            "inline_eq_count": 0,
        }

        chunks = ["This is a test chunk of text."]
        metadatas = [metadata_with_string]

        result = embedder.embed(chunks, metadatas)


        # This should succeed
        assert result.error_message is None, (
            f"Expected success but got error: {result.error_message}"
        )
        assert result.chunk_count == 1


def test_chroma_metadata_with_comma_separated_pages():
    """Verify that ChromaDB accepts comma-separated page numbers as string."""
    import tempfile
    from pathlib import Path

    from rkb.embedders.chroma_embedder import ChromaEmbedder

    with tempfile.TemporaryDirectory() as tmpdir:
        embedder = ChromaEmbedder(db_path=Path(tmpdir) / "test_chroma")

        # Multiple pages as comma-separated string
        metadata_multi_pages = {
            "doc_id": "test_doc",
            "chunk_index": 0,
            "page_numbers": "1,2,3",  # Multiple pages as comma-separated string
            "has_equations": True,
            "display_eq_count": 2,
            "inline_eq_count": 5,
        }

        chunks = ["This chunk spans multiple pages with equations."]
        metadatas = [metadata_multi_pages]

        result = embedder.embed(chunks, metadatas)


        assert result.error_message is None, (
            f"Expected success but got error: {result.error_message}"
        )
        assert result.chunk_count == 1


def test_page_list_conversion_logic():
    """Test the conversion logic from list to string for page numbers."""

    # Test cases for converting page lists to strings
    test_cases = [
        ([1], "1"),
        ([1, 2], "1,2"),
        ([1, 2, 3], "1,2,3"),
        ([5, 6, 7, 8], "5,6,7,8"),
    ]

    for page_list, expected_string in test_cases:
        # This is what we need to do in ingestion_pipeline.py
        result = ",".join(str(p) for p in page_list)
        assert result == expected_string, f"Expected {expected_string}, got {result}"
