# Refactoring Plan: Nugget → RKB Package

This document outlines the step-by-step plan to refactor the existing `nugget/` prototype into the structured `rkb/` package without adding new functionality.

## Overview

**Goal**: Migrate all existing nugget functionality to the rkb package structure while maintaining compatibility with existing data and workflows.

**Strategy**: Bottom-up refactoring starting with core components, then building up through layers.

**Testing**: Each phase has a testable goal to verify functionality is preserved.

## Phase 1: Core Infrastructure
**Goal**: Establish core interfaces and models that existing functionality can build upon.

### Step 1.1: Create Core Models
- [x] Create `rkb/core/models.py` with data classes for:
  - [x] `Document` (represents a PDF/LaTeX file)
  - [x] `ExtractionResult` (output from extractors)
  - [x] `EmbeddingResult` (output from embedders)
  - [x] `SearchResult` (search query results)
  - [x] `ChunkMetadata` (chunk information)

### Step 1.2: Create Core Interfaces
- [x] Create `rkb/core/interfaces.py` with abstract base classes:
  - [x] `ExtractorInterface` (extract method + capabilities)
  - [x] `EmbedderInterface` (embed method + configuration)
  - [x] `ChunkerInterface` (chunk text into segments)

### Step 1.3: Create Core Utilities
- [x] Create `rkb/core/text_processing.py` with utilities:
  - [x] Move `extract_equations()` from `nugget/index.py`
  - [x] Move `chunk_text_by_pages()` from `nugget/index.py`
  - [x] Move `hash_file()` from `nugget/extract.py`

### Step 1.4: Test Core Layer
- [x] Create `tests/unit/test_core/test_models.py`
- [x] Create basic tests for all models and utilities
- [x] **Test Goal**: `pytest tests/unit/test_core` passes

---

## Phase 2: Extractor Layer
**Goal**: Migrate PDF extraction functionality to the extractor layer.

### Step 2.1: Create Extractor Base
- [x] Create `rkb/extractors/base.py` with `get_extractor()` function
- [x] Run `import-linter` and `ruff check` to verify layer compliance

### Step 2.2: Create Chunked Nougat Extractor
- [x] Create `rkb/extractors/nougat_extractor.py`:
  - [x] Implement `ExtractorInterface` first
  - [x] Adapt `extract_pdf_chunks()` from `nugget/robust_extract.py`
  - [x] Return `ExtractionResult` objects
  - [x] Handle chunk processing and error recovery
  - [x] **Note**: Focus only on robust chunked version, not single PDF extraction
- [x] Run `import-linter` and `ruff check` to verify layer compliance

### Step 2.3: Test Extractor Layer
- [x] Create `tests/unit/test_extractors/`
- [x] Test each extractor with sample files
- [x] **Test Goal**: `pytest tests/unit/test_extractors` passes
- [x] **Test Goal**: Extract one PDF and compare output to nugget version

---

## Phase 3: Embedder Layer
**Goal**: Migrate embedding functionality to the embedder layer.

### Step 3.1: Create Ollama Embedder
- [x] Create `rkb/embedders/base.py` with `get_embedder()` function
- [x] Create `rkb/embedders/ollama_embedder.py`:
  - [x] Move `get_ollama_embedding()` from `nugget/index.py` and `nugget/search.py`
  - [x] Implement `EmbedderInterface`
  - [x] Return `EmbeddingResult` objects

### Step 3.2: Create Chroma Embedder
- [x] Create `rkb/embedders/chroma_embedder.py`:
  - [x] Implement Chroma's default embedding model
  - [x] Match existing functionality from `nugget/index.py`

### Step 3.3: Test Embedder Layer
- [x] Create `tests/unit/test_embedders/`
- [x] Test embedding generation with sample text
- [x] **Test Goal**: `pytest tests/unit/test_embedders` passes
- [x] **Test Goal**: Generate embeddings and compare dimensions to nugget version

---

## Phase 4: Pipeline Layer
**Goal**: Migrate document processing workflows to the pipeline layer.

### Step 4.1: Create Document Registry
- [x] Create `rkb/core/document_registry.py`:
  - [x] Implement SQLite-based document tracking
  - [x] Support project organization
  - [x] Handle document versioning and deduplication

### Step 4.2: Create Ingestion Pipeline
- [x] Create `rkb/pipelines/ingestion_pipeline.py`:
  - [x] Move batch processing logic from `nugget/extract.py`
  - [x] Move indexing logic from `nugget/index.py`
  - [x] Integrate extractor and embedder interfaces

### Step 4.3: Create Complete Pipeline
- [x] Create `rkb/pipelines/complete_pipeline.py`:
  - [x] Move `run_pipeline()` from `nugget/pipeline.py`
  - [x] Orchestrate find → extract → index workflow
  - [x] Maintain compatibility with existing data paths

### Step 4.4: Test Pipeline Layer
- [x] Create `tests/integration/test_pipelines/`
- [x] Test end-to-end document processing
- [x] **Test Goal**: `pytest tests/integration/test_pipelines` passes
- [x] **Test Goal**: Process 3 PDFs and verify output matches nugget results

---

## Phase 5: Service Layer
**Goal**: Migrate high-level business logic to the service layer.

### Step 5.1: Create Search Service
- [x] Create `rkb/services/search_service.py`:
  - [x] Move `search_papers()` from `nugget/search.py`
  - [x] Move `display_results()` from `nugget/search.py`
  - [x] Integrate with document registry

### Step 5.2: Create Project Service
- [x] Create `rkb/services/project_service.py`:
  - [x] Implement project creation and management
  - [x] Move `find_recent_pdfs()` from `nugget/find_recent.py`
  - [x] Support document subset selection

### Step 5.3: Create Experiment Service
- [x] Create `rkb/services/experiment_service.py`:
  - [x] Basic experiment creation and management
  - [x] Full experiment comparison functionality

### Step 5.4: Test Service Layer
- [x] Create `tests/unit/test_services/`
- [x] Test search functionality with existing database
- [x] **Test Goal**: `pytest tests/unit/test_services` passes
- [x] **Test Goal**: Search matches results from `nugget/search.py`

---

## Phase 6: CLI Layer
**Goal**: Create command-line interface to replace direct script execution.

### Step 6.1: Create Main CLI
- [x] Create `rkb/cli/main.py`:
  - [x] Implement argparse-based CLI with subcommands
  - [x] `rkb --help` shows available commands

### Step 6.2: Create Search CLI
- [x] Create `rkb/cli/commands/search_cmd.py`:
  - [x] Move `interactive_search()` from `nugget/search.py`
  - [x] `rkb search "query"` command
  - [x] `rkb search --interactive` mode

### Step 6.3: Create Pipeline CLI
- [x] Create `rkb/cli/commands/pipeline_cmd.py`:
  - [x] `rkb extract <path>` command
  - [x] `rkb index <path>` command
  - [x] `rkb pipeline` for complete workflow

### Step 6.4: Create Project CLI
- [x] Create `rkb/cli/commands/project_cmd.py`:
  - [x] `rkb project create` command
  - [x] `rkb project` subcommands (list, show, export, etc.)

### Step 6.5: Create Experiment CLI
- [x] Create `rkb/cli/commands/experiment_cmd.py`:
  - [x] `rkb experiment create` command
  - [x] `rkb experiment compare` command

### Step 6.6: Test CLI Layer
- [x] Test CLI installation and basic functionality
- [x] Test command parsing and help system
- [x] **Test Goal**: `rkb --help` works and shows all commands
- [x] **Test Goal**: All CLI commands parse arguments correctly

---

## Phase 7: Data Migration
**Goal**: Migrate existing nugget data to rkb format.

### Step 7.1: Prepare for Data Recreation
- [x] Document the command sequence for user to recreate data
- [x] Ensure `rkb pipeline run` command works end-to-end
- [x] **Note**: User will run data recreation, not automated in refactoring

---

## Phase 8: Validation & Cleanup
**Goal**: Ensure complete functional parity and clean up.

### Step 8.1: End-to-End Testing
- [x] Create `tests/e2e/test_complete_workflow.py`:
  - [x] Test system integration without full document processing
  - [x] Test experiment management workflow
  - [x] Test error handling and recovery
  - [x] Test data integrity and persistence
  - [x] Test CLI integration points

### Step 8.2: Performance Validation
- [x] Run core and service unit tests (78 tests passing)
- [x] Run end-to-end integration tests (5 tests passing)
- [x] Verify system performance is acceptable


---

## Testing Strategy

### Unit Tests (Per Phase)
- Test individual components in isolation
- Mock external dependencies (Ollama, Chroma)
- Focus on interface compliance

### Integration Tests (Phase 4+)
- Test component interactions
- Use real dependencies where possible
- Verify data flow between layers

### End-to-End Tests (Phase 6+)
- Test complete workflows
- Use real data and services
- Verify output matches nugget results

---

## Dependencies & Prerequisites

### Required Before Starting
- [ ] Package structure exists (`pyproject.toml`, directory layout)
- [ ] Import-linter configuration is working
- [ ] Development environment is set up (`pip install -e ".[dev]"`)

### External Dependencies
- [ ] Ollama service running
- [ ] Test PDFs available

---

## Success Criteria

1. **Functional Parity**: All nugget functionality available through rkb
2. **Data Integrity**: All existing documents searchable through rkb
3. **Performance**: Processing time within 20% of nugget baseline
4. **Architecture Compliance**: import-linter passes on all code
5. **Testing**: Full test suite passes
6. **CLI Usability**: Complete workflows possible through `rkb` commands

---

## Implementation Approach

**Interface-First Development**:
- Implement abstract interfaces first
- Adapt nugget functions to use interfaces
- Don't copy functions directly - refactor to fit architecture

**Quality Assurance**:
- Run `import-linter` after each phase to catch layer violations
- Run `ruff check` and `ruff format` after each phase
- Use real dependencies for testing (Ollama, Chroma)

**Data Strategy**:
- Don't migrate existing nugget data
- User will recreate data using new rkb system
- Focus on functionality, not data preservation

**Iterative Development**:
- Each phase can be completed in a separate session using `/clear`
- Checkboxes allow tracking progress across sessions
- Test goals provide clear success criteria
- Bottom-up approach minimizes dependencies between phases

---

## Phase 9: Pipeline Architecture Fixes
**Goal**: Fix unclear pipeline stage responsibilities causing false failure reports.

### Problem Analysis
Based on CLI_TUTORIAL.md errors, the root cause is **lack of clarity in pipeline stage responsibilities**, not the data model:

1. **IngestionPipeline always runs both extraction AND embedding** - no way to run just extraction
2. **Extract command incorrectly uses embedder** causing false failure reports when extraction succeeds but embedding fails
3. **Mismatched return values** between CompletePipeline.run_pipeline() and CLI expectations
4. **No clear separation of concerns** between extraction and indexing stages

### Step 9.1: Separate Pipeline Responsibilities
- [x] Add `skip_embedding` parameter to IngestionPipeline constructor
- [x] Modify `process_single_document()` to conditionally skip embedding when `skip_embedding=True`
- [x] Update `extract_cmd.py` to use `skip_embedding=True` and remove embedder initialization
- [x] **Test Goal**: `rkb extract` succeeds even with embedding service unavailable

### Step 9.2: Fix Interface Contracts
- [x] Standardize return values from `CompletePipeline.run_pipeline()` to include:
  - `documents_processed`
  - `successful_extractions`
  - `failed_extractions`
  - `successful_embeddings`
  - `failed_embeddings`
- [x] Fix `pipeline_cmd.py` to use correct return value structure
- [x] Add proper `skip_extraction` parameter to CompletePipeline methods
- [x] **Test Goal**: `rkb pipeline` command displays correct statistics

### Step 9.3: Clean Command Separation
- [x] Update `extract_cmd.py`:
  - Remove embedder initialization entirely
  - Use extraction-only pipeline
  - Report only extraction success/failure
- [x] Update `index_cmd.py`:
  - Fix `skip_extraction=True` parameter usage
  - Only process documents with `DocumentStatus.EXTRACTED`
  - Report only embedding/indexing success/failure
- [x] Update `pipeline_cmd.py`:
  - Use full pipeline with both stages
  - Report separate statistics for each stage
- [x] **Test Goal**: Each command has clear, separate responsibilities

### Step 9.4: Improve Error Handling
- [x] Separate extraction errors from embedding errors in status reporting
- [x] Allow partial success reporting (extraction OK, embedding failed)
- [x] Update DocumentStatus transitions to be more granular
- [x] Add proper error context to CLI output
- [x] **Test Goal**: CLI accurately reports what succeeded vs failed

### Step 9.5: Test Architecture Fixes
- [x] Basic functionality tests:
  - Test extraction-only pipeline initialization
  - Test CLI help commands work correctly
  - Test interface compatibility
  - Test proper error handling when no documents found
- [x] Verify CLI commands work as documented in CLI_TUTORIAL.md
- [x] **Test Goal**: All pipeline commands work correctly with clear responsibilities

### Success Criteria
1. **Clear Separation**: Each CLI command has single, well-defined responsibility
2. **Accurate Reporting**: Success/failure reporting matches actual stage outcomes
3. **Error Isolation**: Embedding failures don't affect extraction status and vice versa
4. **Interface Consistency**: Return values match CLI expectations
5. **Tutorial Compliance**: All commands work as documented in CLI_TUTORIAL.md

---

*Document Version: 1.1*
*Created: 2025-09-28*
*Updated: 2025-09-28 - Added Pipeline Architecture Fixes*