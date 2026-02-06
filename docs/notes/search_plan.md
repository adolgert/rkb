# Document Search Implementation Plan

**Created:** 2025-10-02
**Status:** PLANNING
**Goal:** Build document-level search on top of existing chunk-based search

---

## Overview

Transform chunk-based search into document-level search with two ranking metrics:
- **Similarity**: Max pooling (best chunk score per document)
- **Relevance**: Hit counting (chunks above threshold per document)

Key challenge: **Iterative chunk fetching** - query embeddings until we have enough documents, without fetching everything.

---

## Architecture Decisions

- [x] Document search lives in `rkb/services/search_service.py` (extend existing)
- [x] Rename current `rkb search` → `rkb chunks` (for chunk-level search)
- [x] New `rkb search` → document-level search (primary use case)
- [x] Both modes available, no switching needed
- [x] Store minimum threshold as embedding property
- [x] Default top-N = 10 documents (configurable via CLI flag)
- [x] Initial chunk fetch multiplier = N × 5

---

## Phase 1: Core Loop (HIGHEST RISK) ⚠️

**Goal:** Implement the iterative query-rank-fetch loop correctly

### 1.1 Design the Loop Algorithm

- [ ] Write pseudocode for chunk fetching loop
- [ ] Define loop termination conditions:
  - [ ] Have N documents above minimum threshold
  - [ ] Exhausted all chunks in database
  - [ ] Hit maximum fetch limit (safety)
- [ ] Define chunk batch sizes:
  - [ ] Initial fetch: N × 5 chunks
  - [ ] Subsequent fetches: N × 5 chunks
  - [ ] Maximum total chunks: 10,000 (or configurable?)

### 1.2 Implement Chunk Fetcher

**File:** `rkb/services/search_service.py` (extend existing)

- [ ] Add method: `fetch_chunks_iteratively(query, n_docs, min_threshold, metric)`
- [ ] Implement pagination through chunk results
- [ ] Track total chunks fetched
- [ ] Add safety limits to prevent infinite loops
- [ ] Handle case where database has fewer chunks than requested

### 1.3 Test the Loop

**File:** `tests/unit/test_services/test_search_service_document.py`

- [ ] Test: Finds N documents in first fetch
- [ ] Test: Requires multiple fetches to find N documents
- [ ] Test: Stops when exhausting database (< N documents available)
- [ ] Test: Respects maximum chunk limit
- [ ] Test: Handles empty database gracefully
- [ ] Test: Handles query with no results above threshold

**Verification:**
- [ ] All loop tests pass
- [ ] `ruff check` passes
- [ ] `lint-imports` passes

---

## Phase 2: Ranking Metrics

**Goal:** Implement similarity and relevance metrics

### 2.1 Add Minimum Threshold to Embeddings

**File:** `rkb/embedders/base.py` or embedding config

- [ ] Add `minimum_threshold` property to embedder interface
- [ ] Set default threshold = 0.1 (or determine empirically)
- [ ] Make threshold configurable per embedder type
- [ ] Document how to determine threshold for new embedders

### 2.2 Implement Similarity Metric (Max Pooling)

**File:** `rkb/services/search_service.py`

- [ ] Create `rank_by_similarity(chunks) -> list[DocumentScore]`
- [ ] Group chunks by document
- [ ] For each document, take max(chunk scores)
- [ ] Store best chunk score in `best_chunk_score` field
- [ ] Return documents sorted by max score descending

### 2.3 Implement Relevance Metric (Hit Counting)

**File:** `rkb/services/search_service.py`

- [ ] Create `rank_by_relevance(chunks, threshold) -> list[DocumentScore]`
- [ ] Group chunks by document
- [ ] For each document, count chunks where score > threshold
- [ ] Store count in `matching_chunk_count` field
- [ ] Return documents sorted by hit count descending

### 2.4 Create DocumentScore Model (Minimal)

**File:** `rkb/core/models.py`

```python
@dataclass
class DocumentScore:
    """Document-level search result with score.

    Contains only scoring information. Display data (chunks, pages, etc.)
    should be fetched separately using get_display_data().
    """
    doc_id: str
    score: float
    metric_name: str  # "similarity" or "relevance"

    # Metric-specific data (optional, for debugging/analysis)
    matching_chunk_count: int | None = None  # For relevance metric
    best_chunk_score: float | None = None     # For similarity metric
```

- [ ] Add `DocumentScore` model with minimal fields
- [ ] Add serialization methods (for JSON output)
- [ ] Document that display data fetched separately

### 2.5 Test Ranking Metrics

**File:** `tests/unit/test_services/test_search_service_ranking.py`

- [ ] Test similarity: Documents ranked by max chunk score
- [ ] Test similarity: `best_chunk_score` field populated correctly
- [ ] Test relevance: Documents ranked by hit count
- [ ] Test relevance: `matching_chunk_count` field populated correctly
- [ ] Test tie-breaking (if two docs have same score)
- [ ] Test with single-chunk documents
- [ ] Test with multi-chunk documents
- [ ] Test edge case: no chunks above threshold

### 2.6 Test Display Data Fetcher

**File:** `tests/unit/test_services/test_search_service_display.py`

- [ ] Test "top_chunk" strategy returns best chunk
- [ ] Test returned data includes: text, page, score
- [ ] Test with document not in chunk list (graceful handling)
- [ ] Test with document with single chunk
- [ ] Test with document with multiple chunks
- [ ] Test chunk text truncation (if implemented)

**Verification:**
- [ ] All ranking tests pass
- [ ] `ruff check` passes
- [ ] `lint-imports` passes

---

## Phase 3: Service Integration

**Goal:** Wire everything together in SearchService

### 3.1 Add Display Data Fetcher

**File:** `rkb/services/search_service.py`

- [ ] Create `get_display_data(doc_score, chunks, strategy="top_chunk")`
- [ ] Implement "top_chunk" strategy: Return best matching chunk
- [ ] Return display info: chunk text, page number, chunk score
- [ ] Handle case where document has no chunks in result set
- [ ] Add placeholder for future strategies (top_n, all_matching, summary)

### 3.2 Add Document Search Method

**File:** `rkb/services/search_service.py`

- [ ] Create `search_documents(query, metric, top_n, min_threshold)`
- [ ] Call `fetch_chunks_iteratively()` with loop logic
- [ ] Call appropriate ranking function (similarity or relevance)
- [ ] Return top N `DocumentScore` objects
- [ ] Log iteration stats (chunks fetched, iterations, etc.)
- [ ] Store chunks for display data fetching (don't discard)

### 3.3 Integration Tests

**File:** `tests/integration/test_services/test_document_search_integration.py`

- [ ] Test end-to-end: query → chunks → ranking → display data
- [ ] Test with real ChromaDB embedder (mocked)
- [ ] Test with real DocumentRegistry
- [ ] Verify correct number of documents returned
- [ ] Verify scores are in descending order
- [ ] Test display data fetcher with different strategies
- [ ] Verify display data contains correct chunk/page info

**Verification:**
- [ ] All integration tests pass
- [ ] `ruff check` passes
- [ ] `lint-imports` passes

---

## Phase 4: CLI Commands

**Goal:** Expose document search via CLI

### 4.1 Rename Existing Search Command

**File:** `rkb/cli/commands/search_cmd.py`

- [ ] Rename `@click.command(name="search")` → `@click.command(name="chunks")`
- [ ] Update help text: "Search for chunks (low-level)"
- [ ] Keep all existing functionality intact

### 4.2 Create New Search Command

**File:** `rkb/cli/commands/search_cmd.py`

- [ ] Create `@click.command(name="search")`
- [ ] Add arguments:
  - [ ] `query` (required): Search query string
  - [ ] `--metric`: Choice of "similarity" or "relevance" (default: similarity)
  - [ ] `--top-n`: Number of documents to return (default: 10)
  - [ ] `--threshold`: Minimum similarity threshold (default: from embedder)
  - [ ] `--experiment`: Experiment name to search
- [ ] Call `SearchService.search_documents()`
- [ ] Format results with `file://` links

### 4.3 Format Output

**File:** `rkb/cli/commands/search_cmd.py`

Output format:
```
Results for query: "mutation testing automation"
Metric: similarity | Found 10 documents (fetched 237 chunks in 3 iterations)

1. [Score: 0.92] file:///path/to/document.pdf#page=42
   "This chunk discusses mutation testing automation frameworks..."

2. [Score: 0.87] file:///path/to/another.pdf#page=15
   "Advanced techniques for automated mutation analysis..."

...
```

- [ ] Implement formatting function
- [ ] Call `get_display_data()` for each scored document
- [ ] Include rank, score, file:// link with #page=N
- [ ] Include top chunk preview (truncate at 80 chars)
- [ ] Show search stats (chunks fetched, iterations)
- [ ] Handle case with no results
- [ ] Handle case where display data unavailable

### 4.4 CLI Tests

**File:** `tests/integration/test_cli/test_search_commands.py`

- [ ] Test `rkb chunks` still works (renamed command)
- [ ] Test `rkb search` with similarity metric
- [ ] Test `rkb search` with relevance metric
- [ ] Test `rkb search --top-n 20`
- [ ] Test `rkb search --threshold 0.5`
- [ ] Test output format is correct
- [ ] Test clickable file:// links are generated

**Verification:**
- [ ] All CLI tests pass
- [ ] Manual test: Can click links in terminal
- [ ] `ruff check` passes
- [ ] `lint-imports` passes

---

## Phase 5: Documentation & Polish

### 5.1 Update Documentation

- [ ] Update `README.md` with document search examples
- [ ] Add docstrings to all new methods
- [ ] Update `docs/notes/document_search.md` with implementation notes
- [ ] Document how to determine embedder threshold

### 5.2 Add Usage Examples

**File:** `docs/examples/search_documents.md` (new)

- [ ] Example 1: Basic similarity search
- [ ] Example 2: Relevance search with custom threshold
- [ ] Example 3: Searching specific experiment
- [ ] Example 4: Comparing metrics on same query

### 5.3 Final Testing

- [ ] Run full test suite: `pytest`
- [ ] Run linters: `ruff check` and `lint-imports`
- [ ] Test with real PDFs and real embeddings
- [ ] Test edge cases:
  - [ ] Empty database
  - [ ] Single document
  - [ ] Very large database (1000+ docs)
  - [ ] Query with no results

**Verification:**
- [ ] All 240+ tests pass (including ~20 new tests)
- [ ] No linting errors
- [ ] Manual validation successful

---

## Success Criteria

After completing all phases:

1. ✅ Can run `rkb search "query"` and get ranked documents
2. ✅ Can click file:// links to open PDFs at correct page
3. ✅ Both similarity and relevance metrics work correctly
4. ✅ Loop fetches chunks iteratively until N documents found
5. ✅ Handles edge cases (empty DB, no results, etc.)
6. ✅ All tests pass, no linting errors
7. ✅ Old chunk search still available via `rkb chunks`
8. ✅ Clean separation: Ranking only computes scores, display data fetched separately
9. ✅ Display data fetcher extensible for future strategies (top_n, summary, etc.)

---

## Risk Mitigation

### Highest Risk: Iterative Fetch Loop

**Risks:**
- Infinite loop if termination conditions wrong
- Fetch entire database if threshold too low
- Poor performance with large databases
- Off-by-one errors in pagination

**Mitigation:**
- ✅ Implement safety limit (max 10,000 chunks)
- ✅ Write comprehensive loop tests FIRST
- ✅ Add iteration logging for debugging
- ✅ Test with empty/small/large databases

### Medium Risk: Ranking Correctness

**Risks:**
- Incorrect max pooling (e.g., using average instead)
- Threshold comparison off-by-one (> vs ≥)
- Tie-breaking non-deterministic

**Mitigation:**
- ✅ Write ranking tests with known inputs/outputs
- ✅ Test edge cases (ties, single chunk, etc.)
- ✅ Add assertions in code for invariants

### Low Risk: CLI Output Format

**Risks:**
- Links not clickable in all terminals
- Page numbers incorrect or missing

**Mitigation:**
- ✅ Test manually in multiple terminals
- ✅ Add fallback format if page unknown
- ✅ Validate file:// URL format

---

## Timeline Estimate

- **Phase 1 (Core Loop):** 3-4 hours (highest complexity)
- **Phase 2 (Ranking):** 2-3 hours (straightforward logic)
- **Phase 3 (Integration):** 1-2 hours (wiring)
- **Phase 4 (CLI):** 2 hours (formatting, testing)
- **Phase 5 (Polish):** 1 hour (docs, final checks)

**Total:** 9-12 hours (can be split across multiple sessions)

---

## Implementation Order

Follow this order to reduce risk:

1. **Phase 1** → Get the hard part (loop) right first
2. **Phase 2** → Implement ranking (depends on loop working)
3. **Phase 3** → Wire together (depends on both)
4. **Phase 4** → Expose via CLI (user-facing)
5. **Phase 5** → Polish and document

Do NOT proceed to next phase until:
- ✅ All tests for current phase pass
- ✅ `ruff check` passes
- ✅ `lint-imports` passes

---

## Open Questions

- [ ] What's the empirical minimum threshold for ChromaDB embeddings? (Test with sample queries)
- [ ] Should we cache document search results? (Out of scope for MVP)
- [ ] Should we support multiple metrics in one query? (Out of scope for MVP)
- [ ] How to handle documents with no chunks above threshold? (Include in results with score=0 or exclude?)

---

## Notes

- Start with Phase 1 immediately - it's the highest risk
- Write tests FIRST for the loop logic
- Keep chunk-based search available for debugging
- Iterate quickly, test frequently
- Document as you go, not at the end
