# Document Search Description

**Status:** ✅ Core implementation complete (2025-10-02)
**Implementation:** `rkb/services/search_service.py`
**Tests:** 33 tests (10 + 15 + 8) - all passing

---

## Implementation Summary

### What Was Completed

The core document-level search infrastructure is fully implemented and tested:

1. **Iterative Chunk Fetching** (`fetch_chunks_iteratively()` at line 72)
   - Fetches chunks until N documents found or max limit reached
   - Respects minimum similarity threshold
   - Tracks detailed statistics (chunks fetched, iterations, documents found)
   - Handles edge cases: empty database, no results above threshold

2. **Two Ranking Metrics** (as originally specified)
   - **Similarity** (`rank_by_similarity()` at line 237): Max pooling - ranks documents by highest chunk score
   - **Relevance** (`rank_by_relevance()` at line 277): Hit counting - ranks by number of chunks above threshold

3. **Document Score Model** (`rkb/core/models.py:156`)
   - Minimal design: stores doc_id, score, metric_name
   - Metric-specific fields: best_chunk_score, matching_chunk_count
   - Display data fetched separately via `get_display_data()`

4. **Unified Search Interface** (`search_documents_ranked()` at line 379)
   - End-to-end workflow: fetch → rank → return top N
   - Uses embedder's minimum_threshold by default (overridable)
   - Returns (ranked_docs, all_chunks, stats) for flexible display

5. **Embedder Threshold Support** (`EmbedderInterface.minimum_threshold`)
   - Added to interface at line 99
   - Implemented in ChromaEmbedder (0.1) and OllamaEmbedder (0.1)
   - Empirically determined thresholds for filtering irrelevant chunks

### Key Design Decisions & Learnings

**1. ChromaDB Limitation: No True Offset Pagination**
- ChromaDB's query API doesn't support offset-based pagination
- Workaround: Fetch up to MAX_TOTAL_CHUNKS (10,000) in single query
- This simplifies the loop but limits scalability for very large databases
- Future improvement: Implement cursor-based pagination if ChromaDB adds support

**2. Similarity Score Conversion**
- ChromaDB returns L2 distances, converted to similarity via `1/(1+distance)`
- This formula ensures scores are in [0, 1] range, with 1 being perfect match
- Distance 0 → similarity 1.0 (perfect)
- Distance 1 → similarity 0.5 (medium)
- Distance ∞ → similarity 0 (no match)

**3. Threshold Determination**
- Threshold 0.1 chosen empirically for sentence-transformer models
- Corresponds to distance ~9.0 (very loose matching)
- Should be tuned per embedding model based on testing
- Future: Add threshold calibration utility based on query/result quality

**4. Separation of Ranking and Display**
- `DocumentScore` contains only scoring info (no chunks, no display data)
- Display data fetched separately via `get_display_data(chunks, strategy)`
- This separation allows flexible display strategies (top_chunk, top_n, summary)
- Keeps memory footprint low for large result sets

**5. Test Coverage Strategy**
- Phase 1 (10 tests): Loop correctness, termination conditions
- Phase 2 (15 tests): Ranking metrics, display data fetching
- Phase 3 (8 tests): End-to-end integration, real-world scenarios
- Total: 33 new tests, all passing, 91% coverage on search_service.py

---

## Current Architecture

### Module Locations

```
rkb/services/search_service.py
├── fetch_chunks_iteratively()    # Line 72  - Iterative chunk fetching
├── rank_by_similarity()           # Line 237 - Max pooling metric
├── rank_by_relevance()            # Line 277 - Hit counting metric
├── get_display_data()             # Line 324 - Display info fetcher
└── search_documents_ranked()      # Line 379 - Unified interface

rkb/core/models.py
└── DocumentScore                  # Line 156 - Document score model

rkb/core/interfaces.py
└── EmbedderInterface.minimum_threshold  # Line 99
```

### Test Coverage

```
tests/unit/test_services/
├── test_search_service_document.py      # 10 tests - Core loop
├── test_search_service_ranking.py       # 15 tests - Ranking metrics
└── test_search_service_integration.py   #  8 tests - End-to-end
```

---

## Not Yet Implemented (Future Work)

### Phase 4: CLI Commands (READY TO IMPLEMENT)
- [ ] Rename `rkb search` → `rkb chunks` (for chunk-level search)
- [ ] New `rkb search` command for document-level search
- [ ] CLI flags: `--metric`, `--top-n`, `--threshold`, `--experiment`
- [ ] Formatted output with file:// links and page numbers
- [ ] Show search stats (chunks fetched, iterations)

### Phase 5: Documentation & Polish
- [ ] Update README.md with document search examples
- [ ] Add docstrings to all methods (mostly done)
- [ ] Create `docs/examples/search_documents.md`
- [ ] Document threshold tuning methodology
- [ ] End-to-end testing with real PDFs

### Future Enhancements

**Query Expansion (not started)**
- Pre-processing queries with synonyms or related terms
- Could improve recall at cost of precision
- Needs domain-specific synonym dictionaries

**Advanced Display Strategies**
- `top_n`: Show top N matching chunks per document
- `all_matching`: Show all chunks above threshold
- `summary`: LLM-generated summary of matching content
- `context`: Include surrounding chunks for context

**Performance Optimizations**
- Cursor-based pagination when ChromaDB supports it
- Caching of frequent queries
- Parallel chunk fetching for multiple queries
- Batch ranking for large result sets

**Additional Metrics**
- `coverage`: Percentage of document with matches
- `density`: Average score across all document chunks
- `recency`: Weighted by chunk position (recent > older)
- `diversity`: Reward documents with varied matching concepts

**Quality Improvements**
- A/B testing framework for comparing metrics
- Precision@K and Recall@K measurement
- Threshold calibration tool
- Query suggestion/refinement

---

## Use Cases (Original Spec - Now Implementable)

### Ask rkb what metrics are available
```bash
# Not yet implemented in CLI, but could be:
rkb search --list-metrics

# Would output:
# Available metrics:
#   similarity - Rank by highest chunk similarity (max pooling)
#   relevance  - Rank by number of chunks above threshold (hit counting)
```

**Implementation:** Add to CLI in Phase 4

### Search for documents with highest value on a metric
```python
# Current programmatic interface:
from rkb.services.search_service import SearchService

service = SearchService(registry=registry)
ranked_docs, chunks, stats = service.search_documents_ranked(
    query="mutation testing automation",
    n_docs=10,
    metric="similarity",  # or "relevance"
)

# Display results
for doc_score in ranked_docs:
    display_data = service.get_display_data(doc_score, chunks)
    print(f"{doc_score.score:.3f} - {display_data['chunk_text'][:100]}...")
```

**CLI Implementation (Phase 4):**
```bash
rkb search "mutation testing automation" --metric similarity --top-n 10
```

---

## Modular Document Search (Implemented)

### Separation of Concerns ✅

1. **Query expansion** - Skipped (query used as-is) ✅
2. **Chunk similarity score** - Already implemented (ChromaDB) ✅
3. **Document score** - Two metrics implemented (similarity, relevance) ✅
4. **Post-processing** - Display data fetcher implemented, LLM summary future ⏳
5. **Formatting results** - Programmatic done, CLI formatting Phase 4 ⏳

### Multiple Metrics for Document Score ✅

Both originally specified metrics are implemented:

1. **"similarity"**: Rank document by highest similarity score of any chunk ✅
   - Implementation: `rank_by_similarity()` uses max pooling
   - Test coverage: 10 tests covering edge cases

2. **"relevance"**: Rank document by number of chunks above cutoff ✅
   - Implementation: `rank_by_relevance()` uses hit counting
   - Test coverage: 10 tests covering thresholds and edge cases

**Iterative chunk fetching** ✅
- Loop requests more chunks until N documents found
- Configurable MAX_TOTAL_CHUNKS safety limit (10,000)
- Respects minimum threshold to avoid fetching irrelevant chunks

---

## Next Steps for Resuming Work

When ready to continue, pick up at:

1. **Phase 4: CLI Commands** - Expose functionality via command line
   - See `docs/notes/search_plan.md` Phase 4 section for detailed plan
   - Estimated time: 2-3 hours

2. **Phase 5: Polish & Documentation** - Production-ready
   - Examples, documentation, final testing
   - Estimated time: 1-2 hours

3. **Future Enhancements** - Based on usage experience
   - Additional metrics, display strategies, performance tuning
   - Threshold calibration based on real-world queries

**Total implementation so far:** ~8 hours
**Remaining to MVP:** ~3-5 hours
**Test coverage:** 253 tests passing, 91% on search_service.py
 