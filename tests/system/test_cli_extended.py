"""Phase 2: Extended CLI workflow tests."""

import argparse

import pytest

from rkb.cli.commands import extract_cmd, index_cmd, pipeline_cmd, search_cmd


@pytest.mark.slow
@pytest.mark.system
def test_extract_then_index(temp_workspace, sample_pdfs):
    """Test two-step extract then index workflow."""
    # Run extract on PDFs
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

    # Verify extracted status in registry
    from rkb.core.document_registry import DocumentRegistry
    from rkb.core.models import DocumentStatus

    registry = DocumentRegistry(temp_workspace["db_path"])
    extracted_docs = registry.get_documents_by_status(DocumentStatus.EXTRACTED)
    assert len(extracted_docs) > 0, "Should have extracted documents"

    # Run index on extracted docs
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

    # Verify indexed status
    indexed_docs = registry.get_documents_by_status(DocumentStatus.INDEXED)

    # Debug: Print document statuses if indexing failed
    if len(indexed_docs) == 0:
        all_docs = registry.get_all_documents()
        for doc in all_docs:
            print(f"Doc {doc.doc_id[:8]}: status={doc.status.value}")

    assert len(indexed_docs) > 0, "Should have indexed documents"


@pytest.mark.slow
@pytest.mark.system
def test_project_workflow(temp_workspace, sample_pdfs):
    """Test project isolation workflow."""
    # Create project via pipeline with project_name
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
        project_name="test_project",
        verbose=False,
    )
    result = pipeline_cmd.execute(args)
    assert result == 0, "Pipeline command should succeed"

    # Get project ID from registry
    from rkb.core.document_registry import DocumentRegistry

    registry = DocumentRegistry(temp_workspace["db_path"])
    docs = registry.get_all_documents()
    assert len(docs) > 0, "Should have documents"

    project_id = docs[0].project_id
    assert project_id is not None, "Document should have project_id"

    # Search within project
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
        project_id=project_id,
        interactive=False,
        stats=False,
        verbose=False,
    )
    result = search_cmd.execute(args)
    assert result == 0, "Search within project should succeed"


@pytest.mark.slow
@pytest.mark.system
def test_find_command(temp_workspace, sample_pdfs):
    """Test PDF discovery with find command."""
    from rkb.cli.commands import find_cmd

    args = argparse.Namespace(
        data_dir=temp_workspace["data_dir"],
        num_files=10,
        output_file=None,
        project_id=None,
        db_path=temp_workspace["db_path"],
        verbose=False,
    )
    result = find_cmd.execute(args)
    assert result == 0, "Find command should succeed"


@pytest.mark.slow
@pytest.mark.system
def test_stats_and_dry_run(temp_workspace, sample_pdfs):
    """Test non-mutating operations (stats, dry-run)."""
    # First run pipeline to create some data
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

    # Test search with stats
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
        stats=True,
        verbose=False,
    )
    result = search_cmd.execute(args)
    assert result == 0, "Search with stats should succeed"

    # Test dry-run (should not modify anything)
    from rkb.core.document_registry import DocumentRegistry

    registry = DocumentRegistry(temp_workspace["db_path"])
    doc_count_before = len(registry.get_all_documents())

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
        dry_run=True,
        resume=False,
        no_resume=True,
        project_id=None,
        project_name=None,
        verbose=False,
    )
    result = pipeline_cmd.execute(args)
    assert result == 0, "Dry-run should succeed"

    # Verify no new documents were created
    doc_count_after = len(registry.get_all_documents())
    assert doc_count_before == doc_count_after, "Dry-run should not create documents"
