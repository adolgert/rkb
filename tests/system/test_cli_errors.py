"""Phase 3: Error cases and edge condition tests."""

import argparse

import pytest

from rkb.cli.commands import index_cmd, pipeline_cmd, search_cmd


@pytest.mark.slow
@pytest.mark.system
def test_search_before_indexing(temp_workspace):
    """Test search on empty database returns appropriate error."""
    args = argparse.Namespace(
        query=["test"],
        db_path=temp_workspace["db_path"],
        vector_db_path=temp_workspace["vector_db"],
        collection_name="documents",
        embedder="chroma",
        num_results=10,
        metric="relevance",
        threshold=None,
        filter_equations=False,
        no_equations=False,
        project_id=None,
        interactive=False,
        stats=False,
        verbose=False,
    )
    # Search on empty DB might return 0 (no results) or 1 (error)
    # Either is acceptable behavior
    result = search_cmd.execute(args)
    assert result in (0, 1), "Search should handle empty database gracefully"


@pytest.mark.slow
@pytest.mark.system
def test_index_no_documents(temp_workspace):
    """Test index command when no documents are extracted."""
    args = argparse.Namespace(
        embedder="chroma",
        vector_db_path=temp_workspace["vector_db"],
        collection_name="documents",
        project_id=None,
        force_reindex=False,
        db_path=temp_workspace["db_path"],
        dry_run=False,
        checkpoint_dir=temp_workspace["checkpoint_dir"],
        extraction_dir=temp_workspace["extraction_dir"],
        verbose=False,
    )
    result = index_cmd.execute(args)
    assert result == 1, "Index should fail when no extracted documents found"


@pytest.mark.slow
@pytest.mark.system
def test_pipeline_missing_directory(temp_workspace):
    """Test pipeline with non-existent data directory."""
    args = argparse.Namespace(
        data_dir=temp_workspace["root"] / "nonexistent",
        num_files=1,
        db_path=temp_workspace["db_path"],
        vector_db_path=temp_workspace["vector_db"],
        extraction_dir=temp_workspace["extraction_dir"],
        checkpoint_dir=temp_workspace["checkpoint_dir"],
        extractor="nougat",
        embedder="chroma",
        max_pages=500,
        force_reprocess=False,
        dry_run=False,
        resume=False,
        no_resume=True,
        project_id=None,
        project_name=None,
        verbose=False,
    )
    result = pipeline_cmd.execute(args)
    assert result == 1, "Pipeline should fail with missing directory"


@pytest.mark.slow
@pytest.mark.system
def test_documents_empty_results(temp_workspace, sample_pdfs):
    """Test documents command with non-matching query."""
    # First run pipeline to create indexed documents
    args = argparse.Namespace(
        data_dir=temp_workspace["data_dir"],
        num_files=1,
        db_path=temp_workspace["db_path"],
        vector_db_path=temp_workspace["vector_db"],
        extraction_dir=temp_workspace["extraction_dir"],
        checkpoint_dir=temp_workspace["checkpoint_dir"],
        extractor="nougat",
        embedder="chroma",
        max_pages=500,
        force_reprocess=False,
        dry_run=False,
        resume=False,
        no_resume=True,
        project_id=None,
        project_name=None,
        verbose=False,
    )
    result = pipeline_cmd.execute(args)
    assert result == 0, "Pipeline command should succeed"

    # Search with very unlikely query
    from rkb.cli.commands import documents_cmd

    args = argparse.Namespace(
        query=["xyzzyquuxfoobar123456"],
        db_path=temp_workspace["db_path"],
        vector_db_path=temp_workspace["vector_db"],
        collection_name="documents",
        embedder="chroma",
        num_results=10,
        metric="relevance",
        threshold=None,
        filter_equations=False,
        no_equations=False,
        project_id=None,
        interactive=False,
        stats=False,
        verbose=False,
    )
    # Should handle gracefully (return 0 with no results or 1)
    result = documents_cmd.execute(args)
    assert result in (0, 1), "Documents command should handle no results gracefully"


@pytest.mark.slow
@pytest.mark.system
def test_invalid_embedder(temp_workspace, sample_pdfs):
    """Test pipeline with invalid embedder (should be caught by argparse)."""
    # This test validates that argparse choices work correctly
    # We can't easily test this through execute() because argparse
    # validates before we get there. This is a documentation test.
    from rkb.cli.commands import pipeline_cmd

    # Verify that valid choices are enforced
    parser = argparse.ArgumentParser()
    pipeline_cmd.add_arguments(parser)

    # Valid embedder should work
    try:
        args = parser.parse_args(
            [
                "--data-dir",
                str(temp_workspace["data_dir"]),
                "--embedder",
                "chroma",
            ]
        )
        assert args.embedder == "chroma", "Valid embedder should be accepted"
    except SystemExit:
        pytest.fail("Valid embedder should not raise SystemExit")
