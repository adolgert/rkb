# System-Level Test Plan for RKB

## Purpose

Create end-to-end integration tests that verify CLI commands work correctly with real data, using temporary storage locations for all databases and files. These tests will catch bugs where internal pipelines work but CLI commands fail (e.g., documents stored but not findable via `rkb documents`).

## Current State Analysis

### Existing Test Infrastructure

**Unit Tests** (`tests/unit/`):
- Test individual components with mocks
- Good coverage of services, pipelines, embedders
- Use temporary databases via `tempfile.NamedTemporaryFile` - This is a problem because tests should use pytest's tmp_path.

**Integration Tests** (`tests/integration/`):
- Test pipeline operations with real components
- Use temporary directories via `tempfile.TemporaryDirectory` and `tmp_path` fixture. Again, pick the `tmp_path` not the `tempfile`.
- Examples: `test_complete_pipeline.py`, `test_zotero_workflow.py`, `test_checkpoint_resume.py`

**E2E Tests** (`tests/e2e/`):
- `test_complete_workflow.py` - tests service integration but not CLI commands
- Uses `temp_workspace` fixture for directory structure
- Tests registry, project service, experiment service

**Gap Identified**: No tests that exercise the actual CLI commands (`rkb pipeline`, `rkb index`, `rkb search`, `rkb documents`) with real data end-to-end.

### Storage Configuration Analysis

**How paths are currently configured:**

1. **CLI Commands** (`rkb/cli/commands/`):
   - `pipeline_cmd.py`: `--db-path` (default: `rkb_documents.db`), `--vector-db-path` (default: `rkb_chroma_db`)
   - `index_cmd.py`: Same defaults
   - `search_cmd.py`: Same defaults
   - `documents_cmd.py`: Same defaults
   - All commands accept path overrides via arguments

2. **DocumentRegistry** (`rkb/core/document_registry.py`):
   - Constructor: `db_path: Path | str = "rkb_documents.db"`
   - Accepts any path, creates SQLite database at that location

3. **ChromaEmbedder** (`rkb/embedders/chroma_embedder.py`):
   - Constructor: `db_path: Path | str | None = None`
   - Defaults to `"rkb_chroma_db"` if None
   - Accepts any path for Chroma persistent storage

4. **SearchService** (`rkb/services/search_service.py`):
   - Constructor: `db_path: str | Path = "rkb_chroma_db"`
   - Accepts any path for vector database

5. **OllamaEmbedder** (`rkb/embedders/ollama_embedder.py`):
   - No persistent storage, uses HTTP API

**CRITICAL GAP IDENTIFIED**:
- **NougatExtractor** has `output_dir` parameter (defaults to `"rkb_extractions"`)
- **CLI commands do NOT expose this parameter** - they only pass extractor name
- .mmd extraction files are hardcoded to `rkb_extractions/` directory
- **Result**: Cannot redirect extraction output to temporary directories for testing

**Conclusion**: **CODE CHANGES ARE REQUIRED** - must add `--extraction-dir` parameter to CLI commands before system-level testing can work properly.

### CLI Command Testability

**Current approach**: CLI commands are functions that accept `argparse.Namespace` objects:
- `add_arguments(parser)` - adds CLI args
- `execute(args)` - runs the command
- Returns int exit code (0 = success, 1 = failure)

**Testing strategy**:
1. Create `argparse.Namespace` objects with test parameters
2. Point all paths to temporary directories
3. Call `execute(args)` directly
4. Verify exit codes and side effects

**Alternative approach**: Use `subprocess.run()` to call `rkb` CLI directly
- Pros: Tests the actual CLI entry point
- Cons: Slower, harder to debug, requires installation
- Decision: Start with direct function calls, add subprocess tests later if needed. GOOD DECISION!

## Test Plan Phases

### Phase 0: Add Extraction Directory Configuration (PREREQUISITE)

**Goal**: Enable extraction output redirection for isolated testing.

**Problem**:
- NougatExtractor writes .mmd files to `rkb_extractions/` by default
- No CLI parameter exists to override this location
- Tests cannot use temporary directories for full isolation

**Required Changes**:

1. **Add `--extraction-dir` to CLI commands** (`rkb/cli/commands/`):
   - `pipeline_cmd.py`: Add `--extraction-dir` argument (default: `"rkb_extractions"`)
   - `extract_cmd.py`: Add `--extraction-dir` argument
   - `index_cmd.py`: Add `--extraction-dir` argument (needed when reading extracted docs)

2. **Pass extraction_dir through the pipeline chain**:
   - `CompletePipeline.__init__()`: Add `extraction_dir` parameter
   - `IngestionPipeline.__init__()`: Add `extraction_dir` parameter
   - Pass to `get_extractor(extractor_name, max_pages=max_pages, output_dir=extraction_dir)`

3. **Update extractor factory** (`rkb/extractors/base.py`):
   - Modify `get_extractor()` to accept `output_dir` parameter
   - Pass to `NougatExtractor(output_dir=output_dir, ...)`

**Files to modify**:
- `rkb/cli/commands/pipeline_cmd.py`
- `rkb/cli/commands/extract_cmd.py`
- `rkb/cli/commands/index_cmd.py`
- `rkb/pipelines/complete_pipeline.py`
- `rkb/pipelines/ingestion_pipeline.py`
- `rkb/extractors/base.py`

**Implementation approach**:
```python
# In pipeline_cmd.py add_arguments():
parser.add_argument(
    "--extraction-dir",
    type=Path,
    default="rkb_extractions",
    help="Directory for extraction output (default: rkb_extractions)"
)

# In pipeline_cmd.py execute():
pipeline = CompletePipeline(
    registry=registry,
    extractor_name=args.extractor,
    embedder_name=args.embedder,
    project_id=project_id,
    checkpoint_dir=checkpoint_dir,
    extraction_dir=args.extraction_dir,  # NEW
    max_pages=args.max_pages
)

# In IngestionPipeline.__init__():
def __init__(
    self,
    registry: DocumentRegistry | None = None,
    extractor_name: str = "nougat",
    embedder_name: str = "chroma",
    project_id: str | None = None,
    skip_embedding: bool = False,
    checkpoint_dir: Path | None = None,
    max_pages: int = 500,
    extraction_dir: Path | None = None,  # NEW
):
    # ...
    self.extractor = get_extractor(
        extractor_name,
        max_pages=max_pages,
        output_dir=extraction_dir or Path("rkb_extractions")  # NEW
    )
```

**Validation**:
- Manually test: `rkb pipeline --extraction-dir /tmp/test_extractions --data-dir data/initial --num-files 1`
- Verify .mmd files are created in `/tmp/test_extractions/` instead of `rkb_extractions/`
- Run `ruff check`
- Run `lint-imports`
- Run existing tests: `pytest tests/integration/test_pipelines/`

**Exit criteria**:
1. Can specify `--extraction-dir` on CLI commands that do extraction
2. .mmd files are written to specified directory
3. All existing tests still pass
4. No ruff or import-linter errors

---

### Phase 1: Basic CLI Integration Tests

**Goal**: Create system-level tests for the most critical CLI workflows.

**Tests to implement** (`tests/system/test_cli_integration.py`):

1. **test_pipeline_to_search_workflow**
   - Use test data from `data/initial` (copy 1-2 small PDFs to temp dir)
   - Run `rkb pipeline` with temp db paths
   - Verify documents are in registry
   - Run `rkb search` with same paths
   - Verify search returns results
   - **Validates**: Full pipeline + chunk-level search

2. **test_pipeline_to_documents_workflow**
   - Use test data from `data/initial` (copy 1-2 small PDFs to temp dir)
   - Run `rkb pipeline` with temp db paths
   - Verify documents are in registry
   - Run `rkb documents` with same paths
   - Verify documents are found
   - **Validates**: Full pipeline + document-level search (catches the reported bug)

3. **test_index_command_only**
   - Manually create extracted documents in registry
   - Run `rkb index` to embed them
   - Verify embeddings were created
   - Run `rkb search` to confirm searchability
   - **Validates**: Index command in isolation

**Implementation approach**:
```python
import argparse
import shutil
from pathlib import Path
from rkb.cli.commands import pipeline_cmd, search_cmd, documents_cmd, index_cmd

def test_pipeline_to_documents_workflow(tmp_path):
    """Use pytest's tmp_path fixture, NOT tempfile module."""
    workspace = tmp_path / "rkb_test"
    workspace.mkdir()

    # Setup directories
    data_dir = workspace / "data"
    db_path = workspace / "test.db"
    vector_db = workspace / "chroma_db"
    extraction_dir = workspace / "extractions"  # NEW: for .mmd files

    # Copy test PDFs
    data_dir.mkdir()
    shutil.copy("data/initial/sample.pdf", data_dir)

    # Run pipeline with ALL temp paths
    args = argparse.Namespace(
        data_dir=data_dir,
        num_files=1,
        db_path=db_path,
        vector_db_path=vector_db,
        extraction_dir=extraction_dir,  # NEW
        checkpoint_dir=workspace / ".checkpoints",
        extractor="nougat",
        embedder="chroma",
        max_pages=500,
        force_reprocess=False,
        dry_run=False,
        resume=False,
        no_resume=False,
        project_id=None,
        project_name=None,
        verbose=False,
    )
    result = pipeline_cmd.execute(args)
    assert result == 0

    # Verify documents are searchable
    args = argparse.Namespace(
        query=["test"],
        db_path=db_path,
        vector_db_path=vector_db,
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
    assert result == 0  # Should find documents
```

**Validation**:
- Run `pytest tests/system/test_cli_integration.py`
- Run `ruff check`
- Run `lint-imports`

**Exit criteria**: All 3 tests pass with temp storage.

---

### Phase 2: Extended CLI Workflows

**Goal**: Test additional CLI commands and edge cases.

**Tests to implement** (`tests/system/test_cli_extended.py`):

1. **test_extract_then_index**
   - Run `rkb extract` on PDFs
   - Verify extracted status in registry
   - Run `rkb index` on extracted docs
   - Verify indexed status
   - **Validates**: Two-step workflow

2. **test_project_workflow**
   - Create project via `rkb project create`
   - Run pipeline with `--project-id`
   - List project documents via `rkb project list`
   - Search within project
   - **Validates**: Project isolation

3. **test_find_command**
   - Run `rkb find` to discover PDFs
   - Verify output format
   - **Validates**: PDF discovery

4. **test_stats_and_dry_run**
   - Run `rkb search --stats`
   - Run `rkb index --dry-run`
   - Verify no side effects from dry-run
   - **Validates**: Non-mutating operations

**Validation**:
- Run `pytest tests/system/test_cli_extended.py`
- Run `ruff check`
- Run `lint-imports`

**Exit criteria**: All 4 tests pass.

---

### Phase 3: Error Cases and Edge Conditions

**Goal**: Verify error handling and edge cases work correctly via CLI.

**Tests to implement** (`tests/system/test_cli_errors.py`):

1. **test_search_before_indexing**
   - Run `rkb search` on empty database
   - Verify appropriate error message
   - Verify non-zero exit code

2. **test_index_no_documents**
   - Run `rkb index` when no documents extracted
   - Verify error message: "No extracted documents found"
   - Verify exit code 1

3. **test_pipeline_missing_directory**
   - Run `rkb pipeline --data-dir /nonexistent`
   - Verify error handling

4. **test_documents_empty_results**
   - Index documents
   - Search for non-matching query
   - Verify graceful handling of no results

5. **test_invalid_embedder**
   - Run `rkb pipeline --embedder invalid`
   - Verify argument validation error

**Validation**:
- Run `pytest tests/system/test_cli_errors.py`
- Run `ruff check`
- Run `lint-imports`

**Exit criteria**: All 5 tests pass with correct error codes.

---

### Phase 4: Real Data End-to-End Tests

**Goal**: Test complete workflows with actual test data from `data/initial`.

**Tests to implement** (`tests/system/test_cli_real_data.py`):

1. **test_full_pipeline_with_real_pdf**
   - Select 1 real PDF from `data/initial` (smallest file)
   - Run full pipeline: extract + embed
   - Verify document is searchable
   - Perform real searches with different queries
   - Verify chunk-level and document-level results
   - **Validates**: Real extraction (Nougat) + real embedding (Chroma)
   - **Note**: This test will be slower, may require GPU for Nougat

2. **test_multiple_pdfs_ranking**
   - Process 2-3 real PDFs
   - Search with query that should match specific documents
   - Verify ranking/ordering makes sense
   - **Validates**: Multi-document search and ranking

3. **test_checkpoint_resume_via_cli**
   - Start pipeline with 3 PDFs
   - Interrupt after processing 1 (mock interruption via checkpoint manipulation)
   - Resume with `--resume` flag
   - Verify only remaining PDFs are processed
   - **Validates**: Checkpoint system via CLI

**Special considerations**:
- Use `@pytest.mark.slow` decorator for these tests
- Use `@pytest.mark.requires_gpu` if Nougat requires GPU on your system
- **DO NOT mock Nougat** - use real extraction to validate end-to-end behavior
- Tests will be slower due to actual PDF processing
- Local execution only (no CI/CD assumed)

**Validation**:
- Run `pytest tests/system/test_cli_real_data.py`
- Run `ruff check`
- Run `lint-imports`

**Exit criteria**: All 3 tests pass (or skipped with appropriate markers).

---

### Phase 5: Cross-Command State Consistency

**Goal**: Verify state consistency across different CLI invocations.

**Tests to implement** (`tests/system/test_cli_state.py`):

1. **test_persistent_state_across_commands**
   - Run `rkb pipeline` to create documents
   - Exit and re-run `rkb search` (new process simulation)
   - Verify documents are still searchable
   - **Validates**: Database persistence

2. **test_force_reindex**
   - Run pipeline to index documents
   - Modify a document in registry (update metadata)
   - Run `rkb index --force-reindex`
   - Verify re-indexing occurred
   - **Validates**: Force reprocess flag

3. **test_incremental_pipeline_runs**
   - Run pipeline on 2 PDFs
   - Add 1 more PDF to directory
   - Run pipeline again (should skip existing)
   - Verify only new PDF processed
   - **Validates**: Incremental processing

**Validation**:
- Run `pytest tests/system/test_cli_state.py`
- Run `ruff check`
- Run `lint-imports`

**Exit criteria**: All 3 tests pass.

---

## Test Infrastructure Setup

### Directory Structure
```
tests/
├── system/                      # New directory for system-level tests
│   ├── __init__.py
│   ├── conftest.py              # Shared fixtures
│   ├── test_cli_integration.py  # Phase 1
│   ├── test_cli_extended.py     # Phase 2
│   ├── test_cli_errors.py       # Phase 3
│   ├── test_cli_real_data.py    # Phase 4
│   └── test_cli_state.py        # Phase 5
├── integration/                 # Existing
├── unit/                        # Existing
└── e2e/                         # Existing
```

### Shared Fixtures (`tests/system/conftest.py`)

**IMPORTANT**: Use pytest's `tmp_path` fixture, NOT `tempfile` module.

```python
import pytest
import shutil
from pathlib import Path

@pytest.fixture
def temp_workspace(tmp_path):
    """Create temporary workspace with standard directory structure.

    Uses pytest's tmp_path fixture (NOT tempfile module).
    tmp_path is automatically cleaned up after test completion.
    """
    workspace = tmp_path / "rkb_test"
    workspace.mkdir()

    # Standard directories
    (workspace / "data").mkdir()
    (workspace / "extractions").mkdir()  # For .mmd files

    yield {
        "root": workspace,
        "data_dir": workspace / "data",
        "db_path": workspace / "test.db",
        "vector_db": workspace / "chroma_db",
        "extraction_dir": workspace / "extractions",  # NEW
        "checkpoint_dir": workspace / ".checkpoints",
    }

@pytest.fixture
def sample_pdfs(temp_workspace):
    """Copy sample PDFs from test data to temp workspace."""
    data_initial = Path("data/initial")
    if not data_initial.exists():
        pytest.skip("No test data available in data/initial")

    # Copy first 2 smallest PDFs
    pdf_files = sorted(data_initial.glob("*.pdf"), key=lambda p: p.stat().st_size)[:2]

    copied_files = []
    for pdf in pdf_files:
        dest = temp_workspace["data_dir"] / pdf.name
        shutil.copy(pdf, dest)
        copied_files.append(dest)

    return copied_files

@pytest.fixture
def cli_args_base(temp_workspace):
    """Base CLI arguments with temp paths for all storage locations."""
    return {
        "db_path": temp_workspace["db_path"],
        "vector_db_path": temp_workspace["vector_db"],
        "extraction_dir": temp_workspace["extraction_dir"],  # NEW
        "checkpoint_dir": temp_workspace["checkpoint_dir"],
        "verbose": False,
    }
```

### Pytest Configuration

Add to `pyproject.toml` or `pytest.ini`:
```ini
[tool.pytest.ini_options]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "requires_gpu: marks tests requiring GPU",
    "requires_ollama: marks tests requiring Ollama service",
    "system: marks system-level integration tests",
]
```

### Local Development Testing

**ASSUMPTION**: No GitHub CI/CD for now, all tests run locally.

**Running tests**:
```bash
# Run only fast system tests
pytest tests/system -m "not slow and not requires_gpu"

# Run all system tests
pytest tests/system

# Run specific phase
pytest tests/system/test_cli_integration.py
```

## Implementation Checklist (Per Phase)

For each phase:

- [ ] Create test file
- [ ] Implement test functions
- [ ] Add necessary fixtures to `conftest.py`
- [ ] Run tests locally: `pytest tests/system/test_*.py -v`
- [ ] Run code quality: `ruff check`
- [ ] Run import linter: `lint-imports`
- [ ] Fix any issues
- [ ] Verify all tests pass
- [ ] Commit changes

## Success Criteria

**Phase completion**: Each phase is complete when:
1. All tests in that phase pass
2. `ruff check` passes with no errors
3. `lint-imports` passes with no errors
4. Code coverage maintained or improved

**Overall completion**: All phases (0-5) complete and:
1. Can run `pytest tests/system` with all tests passing
2. System-level tests catch the original bug (documents not findable via `rkb documents`)
3. All storage uses temporary directories (SQLite, ChromaDB, .mmd extractions)
4. Tests use pytest's `tmp_path`, not `tempfile` module

## Maintenance and Evolution

**Adding new CLI commands**:
1. Add corresponding system test in Phase 2
2. Add error test in Phase 3
3. Update fixtures if new storage is needed

**Adding new features**:
1. Add system test demonstrating feature works end-to-end
2. Ensure test uses temporary storage
3. Add to appropriate phase

**Debugging failures**:
1. System tests will preserve temp directories on failure (pytest `--basetemp`)
2. Can inspect SQLite databases with `sqlite3`
3. Can inspect Chroma databases by opening with ChromaDB client
4. Verbose mode (`-v`) shows full CLI output

## Summary

**Phase 0 is a prerequisite** - must implement `--extraction-dir` parameter before other phases can work.

**Key principles**:
- **Phase 0 REQUIRED**: Add `--extraction-dir` CLI parameter for .mmd output control
- **Use tmp_path**: All tests use pytest's `tmp_path` fixture, NOT `tempfile` module
- **Incremental approach**: Each phase builds on previous phases
- **Real extraction**: Phase 4 uses actual Nougat, not mocks
- **Isolated tests**: Each test uses fresh temporary directory via `tmp_path`
- **Local execution**: No CI/CD assumptions, all tests run locally
- **Complete isolation**: All storage (SQLite, ChromaDB, .mmd files) redirected to temp paths
