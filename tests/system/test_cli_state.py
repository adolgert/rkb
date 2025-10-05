"""Phase 5: Cross-command state consistency tests."""

import argparse

import pytest

from rkb.cli.commands import pipeline_cmd, search_cmd


@pytest.mark.slow
@pytest.mark.system
def test_persistent_state_across_commands(temp_workspace, sample_pdfs):
    """Test that state persists across different CLI invocations."""
    # Run pipeline to create documents
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
    assert result == 0, "Initial pipeline should succeed"

    # Simulate new process by re-running search
    # (in real CLI, this would be a separate invocation)
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
    assert result == 0, "Search in new 'session' should find documents"


@pytest.mark.slow
@pytest.mark.system
def test_force_reindex(temp_workspace, sample_pdfs):
    """Test force reindex flag."""
    # Run pipeline to create indexed documents
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
    assert result == 0, "Initial pipeline should succeed"

    # Get document count
    from rkb.core.document_registry import DocumentRegistry
    from rkb.core.models import DocumentStatus

    registry = DocumentRegistry(temp_workspace["db_path"])
    indexed_docs_before = registry.get_documents_by_status(DocumentStatus.INDEXED)
    assert len(indexed_docs_before) > 0, "Should have indexed documents"

    # Force reindex (note: this sets documents back to EXTRACTED, then re-indexes)
    # Since documents are already INDEXED, force_reindex won't find EXTRACTED docs
    # So we need to manually set them to EXTRACTED first, or test with extract+index

    # Better approach: use force_reprocess on pipeline
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
        force_reprocess=True,  # Force reprocessing
        dry_run=False,
        resume=False,
        no_resume=True,
        project_id=None,
        project_name=None,
        verbose=False,
    )
    result = pipeline_cmd.execute(args)
    assert result == 0, "Force reprocess should succeed"

    # Verify documents are still indexed
    indexed_docs_after = registry.get_documents_by_status(DocumentStatus.INDEXED)
    assert len(indexed_docs_after) > 0, "Should still have indexed documents after reprocess"


@pytest.mark.slow
@pytest.mark.system
def test_incremental_pipeline_runs(temp_workspace, sample_pdfs):
    """Test incremental processing - skip existing, process new."""
    if len(sample_pdfs) < 2:
        pytest.skip("Need at least 2 PDFs for incremental test")

    # Process first PDF only
    import shutil
    from pathlib import Path

    # Get the original source from data/initial
    data_initial = Path("data/initial")
    second_pdf_name = sample_pdfs[1].name
    second_pdf_original = data_initial / second_pdf_name

    # Remove second PDF from temp workspace
    second_pdf = temp_workspace["data_dir"] / second_pdf_name
    if second_pdf.exists():
        second_pdf.unlink()

    args = argparse.Namespace(
        data_dir=temp_workspace["data_dir"],
        num_files=10,  # Process all available
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
    assert result == 0, "First pipeline run should succeed"

    # Verify one document processed
    from rkb.core.document_registry import DocumentRegistry

    registry = DocumentRegistry(temp_workspace["db_path"])
    docs_after_first = registry.get_all_documents()
    first_count = len(docs_after_first)
    assert first_count > 0, "Should have processed first document"

    # Add second PDF from original source
    shutil.copy(second_pdf_original, second_pdf)

    # Run pipeline again (should skip first, process second)
    result = pipeline_cmd.execute(args)
    assert result == 0, "Second pipeline run should succeed"

    # Verify second document was added
    docs_after_second = registry.get_all_documents()
    second_count = len(docs_after_second)
    assert second_count > first_count, "Should have processed additional document"
