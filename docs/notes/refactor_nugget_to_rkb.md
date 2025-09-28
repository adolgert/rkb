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
- [ ] Create `rkb/core/document_registry.py`:
  - [ ] Implement SQLite-based document tracking
  - [ ] Support project organization
  - [ ] Handle document versioning and deduplication

### Step 4.2: Create Ingestion Pipeline
- [ ] Create `rkb/pipelines/ingestion_pipeline.py`:
  - [ ] Move batch processing logic from `nugget/extract.py`
  - [ ] Move indexing logic from `nugget/index.py`
  - [ ] Integrate extractor and embedder interfaces

### Step 4.3: Create Complete Pipeline
- [ ] Create `rkb/pipelines/complete_pipeline.py`:
  - [ ] Move `run_pipeline()` from `nugget/pipeline.py`
  - [ ] Orchestrate find → extract → index workflow
  - [ ] Maintain compatibility with existing data paths

### Step 4.4: Test Pipeline Layer
- [ ] Create `tests/integration/test_pipelines/`
- [ ] Test end-to-end document processing
- [ ] **Test Goal**: `pytest tests/integration/test_pipelines` passes
- [ ] **Test Goal**: Process 3 PDFs and verify output matches nugget results

---

## Phase 5: Service Layer
**Goal**: Migrate high-level business logic to the service layer.

### Step 5.1: Create Search Service
- [ ] Create `rkb/services/search_service.py`:
  - [ ] Move `search_papers()` from `nugget/search.py`
  - [ ] Move `display_results()` from `nugget/search.py`
  - [ ] Integrate with document registry

### Step 5.2: Create Project Service
- [ ] Create `rkb/services/project_service.py`:
  - [ ] Implement project creation and management
  - [ ] Move `find_recent_pdfs()` from `nugget/find_recent.py`
  - [ ] Support document subset selection

### Step 5.3: Create Experiment Service
- [ ] Create `rkb/services/experiment_service.py`:
  - [ ] Basic experiment creation and management
  - [ ] Placeholder for comparison functionality

### Step 5.4: Test Service Layer
- [ ] Create `tests/unit/test_services/`
- [ ] Test search functionality with existing database
- [ ] **Test Goal**: `pytest tests/unit/test_services` passes
- [ ] **Test Goal**: Search matches results from `nugget/search.py`

---

## Phase 6: CLI Layer
**Goal**: Create command-line interface to replace direct script execution.

### Step 6.1: Create Main CLI
- [ ] Create `rkb/cli/main.py`:
  - [ ] Implement Click-based CLI with subcommands
  - [ ] `rkb --help` shows available commands

### Step 6.2: Create Search CLI
- [ ] Create `rkb/cli/search.py`:
  - [ ] Move `interactive_search()` from `nugget/search.py`
  - [ ] `rkb search "query"` command
  - [ ] `rkb search --interactive` mode

### Step 6.3: Create Pipeline CLI
- [ ] Create `rkb/cli/pipeline.py`:
  - [ ] `rkb extract <path>` command
  - [ ] `rkb index <path>` command
  - [ ] `rkb pipeline run` for complete workflow

### Step 6.4: Create Project CLI
- [ ] Create `rkb/cli/project.py`:
  - [ ] `rkb project create` command
  - [ ] `rkb project add-documents` command

### Step 6.5: Test CLI Layer
- [ ] Create `tests/e2e/test_cli/`
- [ ] Test all CLI commands
- [ ] **Test Goal**: `pytest tests/e2e/test_cli` passes
- [ ] **Test Goal**: `rkb search "hazard rate"` returns results

---

## Phase 7: Data Migration
**Goal**: Migrate existing nugget data to rkb format.

### Step 7.1: Prepare for Data Recreation
- [ ] Document the command sequence for user to recreate data
- [ ] Ensure `rkb pipeline run` command works end-to-end
- [ ] **Note**: User will run data recreation, not automated in refactoring

---

## Phase 8: Validation & Cleanup
**Goal**: Ensure complete functional parity and clean up.

### Step 8.1: End-to-End Testing
- [ ] Create `tests/e2e/test_complete_workflow.py`:
  - [ ] Process 5 PDFs from scratch using rkb

### Step 8.2: Performance Validation
- [ ] Run `rkb pipeline run` on existing dataset


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

*Document Version: 1.0*
*Created: 2025-09-28*