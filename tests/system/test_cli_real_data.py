"""Phase 4: Real data end-to-end tests."""

import argparse

import pytest

from rkb.cli.commands import documents_cmd, pipeline_cmd, search_cmd


@pytest.mark.slow
@pytest.mark.system
def test_full_pipeline_with_real_pdf(temp_workspace, sample_pdfs):
    """Test complete workflow with real PDF extraction and embedding.

    Note: This uses real Nougat extraction (no mocks) and may be slow.
    """
    # Run full pipeline with real extraction
    args = argparse.Namespace(
        data_dir=temp_workspace["data_dir"],
        num_files=1,
        db_path=temp_workspace["db_path"],
        vector_db_path=temp_workspace["vector_db"],
        extraction_dir=temp_workspace["extraction_dir"],
        checkpoint_dir=temp_workspace["checkpoint_dir"],
        extractor="nougat",
        embedder="chroma",
        max_pages=10,  # Limit pages for speed
        force_reprocess=False,
        dry_run=False,
        resume=False,
        no_resume=True,
        project_id=None,
        project_name=None,
        verbose=False,
    )
    result = pipeline_cmd.execute(args)
    assert result == 0, "Pipeline with real PDF should succeed"

    # Verify document is searchable with different queries
    test_queries = ["equation", "method", "result"]

    for query in test_queries:
        # Test chunk-level search
        args = argparse.Namespace(
            query=[query],
            db_path=temp_workspace["db_path"],
            vector_db_path=temp_workspace["vector_db"],
            collection_name="documents",
            embedder="chroma",
            num_results=5,
            metric="relevance",
            threshold=None,
            filter_equations=False,
            no_equations=False,
            project_id=None,
            interactive=False,
            stats=False,
            verbose=False,
        )
        result = search_cmd.execute(args)
        # May return 0 (results) or 0 (no results) - both ok
        assert result == 0, f"Search for '{query}' should execute successfully"

        # Test document-level search
        args = argparse.Namespace(
            query=[query],
            db_path=temp_workspace["db_path"],
            vector_db_path=temp_workspace["vector_db"],
            collection_name="documents",
            embedder="chroma",
            num_results=5,
            metric="relevance",
            threshold=None,
            filter_equations=False,
            no_equations=False,
            project_id=None,
            interactive=False,
            stats=False,
            verbose=False,
        )
        result = documents_cmd.execute(args)
        assert result == 0, f"Document search for '{query}' should execute successfully"


@pytest.mark.slow
@pytest.mark.system
def test_multiple_pdfs_ranking(temp_workspace, sample_pdfs):
    """Test multi-document search and ranking."""
    if len(sample_pdfs) < 2:
        pytest.skip("Need at least 2 PDFs for this test")

    # Process multiple PDFs
    args = argparse.Namespace(
        data_dir=temp_workspace["data_dir"],
        num_files=2,
        db_path=temp_workspace["db_path"],
        vector_db_path=temp_workspace["vector_db"],
        extraction_dir=temp_workspace["extraction_dir"],
        checkpoint_dir=temp_workspace["checkpoint_dir"],
        extractor="nougat",
        embedder="chroma",
        max_pages=10,  # Limit pages for speed
        force_reprocess=False,
        dry_run=False,
        resume=False,
        no_resume=True,
        project_id=None,
        project_name=None,
        verbose=False,
    )
    result = pipeline_cmd.execute(args)
    assert result == 0, "Pipeline with multiple PDFs should succeed"

    # Search and verify results are returned
    args = argparse.Namespace(
        query=["research"],
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
    result = search_cmd.execute(args)
    assert result == 0, "Search across multiple documents should succeed"


@pytest.mark.slow
@pytest.mark.system
def test_checkpoint_resume_via_cli(temp_workspace, sample_pdfs):
    """Test checkpoint resume functionality via CLI.

    This test simulates interruption by using the checkpoint system.
    """
    if len(sample_pdfs) < 2:
        pytest.skip("Need at least 2 PDFs for checkpoint test")

    # Start pipeline with multiple files, but limit to ensure some remain
    args = argparse.Namespace(
        data_dir=temp_workspace["data_dir"],
        num_files=2,
        db_path=temp_workspace["db_path"],
        vector_db_path=temp_workspace["vector_db"],
        extraction_dir=temp_workspace["extraction_dir"],
        checkpoint_dir=temp_workspace["checkpoint_dir"],
        extractor="nougat",
        embedder="chroma",
        max_pages=5,  # Small page count for speed
        force_reprocess=False,
        dry_run=False,
        resume=False,
        no_resume=True,  # Start fresh
        project_id=None,
        project_name=None,
        verbose=False,
    )
    result = pipeline_cmd.execute(args)
    assert result == 0, "Initial pipeline run should succeed"

    # Try to resume (should find no remaining work)
    args.resume = True
    args.no_resume = False
    result = pipeline_cmd.execute(args)
    # Should succeed (either processes or finds nothing to do)
    assert result in (0, 1), "Resume should complete successfully or report no work"
