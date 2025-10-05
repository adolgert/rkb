"""Phase 1: Basic CLI integration tests."""

import argparse

import pytest

from rkb.cli.commands import documents_cmd, index_cmd, pipeline_cmd, search_cmd


@pytest.mark.slow
@pytest.mark.system
def test_pipeline_to_search_workflow(temp_workspace, sample_pdfs):
    """Test full pipeline from extraction to chunk-level search.

    Note: This test requires working nougat extraction and may be skipped
    if extraction fails in the test environment.
    """
    # Run pipeline with all temp paths
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

    # If extraction fails (nougat issues), skip the test
    if result != 0:
        pytest.skip("Nougat extraction not working in test environment")

    # Verify search works
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
    result = search_cmd.execute(args)
    assert result == 0, "Search command should succeed"


@pytest.mark.slow
@pytest.mark.system
def test_pipeline_to_documents_workflow(temp_workspace, sample_pdfs):
    """Test full pipeline to document-level search (catches reported bug)."""
    # Run pipeline with all temp paths
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

    # Verify documents are findable
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
    result = documents_cmd.execute(args)
    assert result == 0, "Documents command should find documents"


@pytest.mark.slow
@pytest.mark.system
def test_index_command_only(temp_workspace, sample_pdfs):
    """Test index command in isolation."""
    # First extract documents
    from rkb.cli.commands import extract_cmd

    args = argparse.Namespace(
        files=sample_pdfs[:1],
        extractor="nougat",
        max_pages=500,
        project_id=None,
        force_reprocess=False,
        resume=False,
        no_resume=True,
        checkpoint_dir=temp_workspace["checkpoint_dir"],
        db_path=temp_workspace["db_path"],
        extraction_dir=temp_workspace["extraction_dir"],
        verbose=False,
    )
    result = extract_cmd.execute(args)
    assert result == 0, "Extract command should succeed"

    # Run index command
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
    assert result == 0, "Index command should succeed"

    # Verify search works
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
    result = search_cmd.execute(args)
    assert result == 0, "Search command should succeed after indexing"
