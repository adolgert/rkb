# RAG Search Title Integration Analysis

**Date:** 2025-11-15
**Topic:** Integrating title metadata into RAG search pipeline

## Executive Summary

The RKB system currently **has infrastructure for titles but doesn't use it**. Documents are indexed without titles, and the RAG search displays results using only `doc_id` or `pdf_name`. A separate metadata extraction system exists (`build_metadata_db.py`) that uses Gemma2 LLM to extract titles, but this data is stored in an isolated JSON file and never integrated back into the main pipeline.

**Difficulty Assessment:** **MEDIUM** - The infrastructure exists, but requires bridging three disconnected systems and handling title updates gracefully.

---

## Current State: How Titles Are (Not) Handled

### 1. Document Registry Has Title Storage (But It's Empty)

**File:** `rkb/core/document_registry.py`

The SQLite `documents` table has a `title` field:

```sql
CREATE TABLE documents (
    doc_id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    content_hash TEXT,
    title TEXT,              -- ← Field exists but never populated!
    authors TEXT,
    arxiv_id TEXT,
    doi TEXT,
    ...
)
```

**Problem:** When documents are created during ingestion, titles are set to `None`:

```python
# rkb/core/document_registry.py:478-484
document = Document(
    doc_id=doc_identity.doc_id,
    source_path=source_path,
    content_hash=doc_identity.content_hash,
    status=DocumentStatus.PENDING,
    project_id=project_id,
    # title is NOT set here - defaults to None
)
```

### 2. Hash-Based Document Identification (The Confusion)

You mentioned the pipeline "mixes up SHA and MD5" - this is accurate:

| Hash Type | Purpose | Location |
|-----------|---------|----------|
| **SHA-256** | Primary document identity & deduplication | `rkb/core/identity.py:22-32` |
| **MD5** | Metadata database key (build_metadata_db.py) | `rkb/core/text_processing.py` |

**Why two hashes?**
- SHA-256 is used in the main pipeline for `DocumentIdentity` and `content_hash` in the registry
- MD5 is used separately by `build_metadata_db.py` to cache metadata extraction results

**This creates a disconnect:** Metadata is keyed by MD5 hash, but documents in the registry are identified by SHA-256 hash and doc_id (UUID).

### 3. Metadata Extraction System (Isolated from Pipeline)

**File:** `rkb/cli/build_metadata_db.py`

This is the script you mentioned that uses "local model and web searches":

```python
extractor = Gemma2Extractor()  # Uses local Ollama model (gemma2:9b-instruct-q4_K_M)
```

**What it does:**
1. Scans a directory for PDFs
2. Computes **MD5 hash** for each file
3. Extracts metadata using 5 sources:
   - PDF metadata fields (PyMuPDF)
   - Filename patterns (author, year, arXiv ID)
   - First page parsing (title heuristics)
   - GROBID (ML-based academic paper parser)
   - DOI/CrossRef API lookup ← **This is the "web search" component**
4. Uses Gemma2 LLM to reconcile conflicts and pick best values
5. Stores results in `data/metadata_db.json` keyed by MD5 hash

**Storage format:**
```json
{
  "md5_hash_here": {
    "doc_type": "article",
    "title": "Deep Learning for Scientific Computing",
    "authors": ["Smith, J.", "Doe, A."],
    "year": 2023,
    "journal": "Nature",
    "page_count": 12
  }
}
```

**Problem:** This JSON file is **never read by the RAG pipeline**. It's a dead end.

### 4. RAG Search Display (No Titles Shown)

**File:** `rkb/services/search_service.py:717-780`

```python
def display_results(self, search_result: SearchResult, ...):
    for i, chunk in enumerate(search_result.chunk_results):
        # Shows pdf_name or doc_id, but NOT title
        if "pdf_name" in metadata:
            print(f"📄 Source: {metadata['pdf_name']} (chunk {chunk_idx})")
        elif "doc_id" in metadata:
            print(f"📄 Document: {metadata['doc_id']}")  # ← UUID, not human-readable!
```

**User Experience:** Search results show cryptic UUIDs like `📄 Document: a7f3c8d2-...` instead of meaningful titles.

---

## Gap Analysis: What's Missing

### Missing Component 1: Update Document Titles in Registry

**Problem:** No method exists to update document metadata after creation.

**Needed:**
```python
# rkb/core/document_registry.py - DOES NOT EXIST YET
def update_document_metadata(
    self,
    doc_id: str,
    title: str | None = None,
    authors: list[str] | None = None,
    arxiv_id: str | None = None,
    doi: str | None = None
) -> bool:
    """Update document metadata fields."""
    # SQL UPDATE statement to modify title, authors, etc.
```

### Missing Component 2: Bridge Between Hashing Systems

**Problem:** Metadata is keyed by MD5, but registry uses SHA-256 and doc_id.

**Options:**
1. **Add MD5 column to registry** - Store both hashes for lookup
2. **Recompute MD5 from source_path** - When looking up metadata
3. **Migrate metadata DB to use SHA-256** - Change build_metadata_db.py to use SHA-256

**Recommendation:** Option 2 is simplest - compute MD5 on-the-fly when needed.

### Missing Component 3: Metadata Integration Step

**Problem:** No pipeline step populates titles from metadata DB.

**Needed:** A new command or pipeline stage:
```bash
rkb sync-metadata --metadata-db data/metadata_db.json --db-path rkb_documents.db
```

This would:
1. Iterate through all documents in registry
2. Compute MD5 hash from source_path
3. Lookup metadata in JSON file
4. Update document title/authors/doi/arxiv_id

### Missing Component 4: Display Titles in Search Results

**Problem:** `search_service.display_results()` doesn't fetch or show titles.

**Needed:**
```python
# rkb/services/search_service.py:display_results()
doc_id = chunk.metadata.get("doc_id")
if doc_id:
    # NEW: Fetch document from registry
    doc = self.registry.get_document(doc_id)
    if doc and doc.title:
        print(f"📄 {doc.title}")
    else:
        print(f"📄 Document: {doc_id}")
```

---

## Implementation Roadmap

### Phase 1: Enable Title Updates (Low Risk)

**Estimated Effort:** 2-3 hours

1. **Add `update_document_metadata()` method to DocumentRegistry**
   - File: `rkb/core/document_registry.py`
   - SQL UPDATE statement for title, authors, arxiv_id, doi
   - Return True if successful, False if doc not found
   - Update `updated_date` timestamp

2. **Add tests for metadata updates**
   - File: `tests/test_document_registry.py`
   - Test updating title
   - Test updating authors
   - Test updating when doc doesn't exist
   - Test partial updates (only title, not authors)

**Benefits:**
- Enables future title management
- Low risk - doesn't change existing behavior
- Allows manual title setting

### Phase 2: Sync Existing Metadata (Medium Risk)

**Estimated Effort:** 4-6 hours

1. **Create `sync_metadata` CLI command**
   - File: `rkb/cli/commands/sync_metadata_cmd.py`
   - Read metadata from `data/metadata_db.json` (MD5-keyed)
   - For each document in registry:
     - Compute MD5 from source_path
     - Lookup in metadata DB
     - Update title/authors/doi/arxiv_id if found
   - Report stats: how many updated, how many missing, errors

2. **Handle hash bridge gracefully**
   - Option: Compute MD5 on-the-fly from source_path
   - Option: Store MD5 in registry for faster lookup (add column)
   - Handle missing files (source_path no longer exists)

3. **Add dry-run and verbose modes**
   - `--dry-run`: Show what would be updated without changing
   - `--verbose`: Show each update operation
   - `--force`: Overwrite existing titles (default: skip if title exists)

**Benefits:**
- Populate existing registry with titles from metadata DB
- One-time migration tool
- Can be re-run as metadata is improved

### Phase 3: Display Titles in Search Results (Low Risk)

**Estimated Effort:** 2-3 hours

1. **Modify `display_results()` to fetch and show titles**
   - File: `rkb/services/search_service.py:717-780`
   - For each result, call `self.registry.get_document(doc_id)`
   - Display title if available, fallback to doc_id
   - Add authors if available
   - Show source_path for context

2. **Enhance document-level search display**
   - File: `rkb/services/search_service.py:search_documents_ranked()`
   - Already returns DocumentScore objects with doc_id
   - Enrich with title/authors before display

**Example new output:**
```
📊 Found 5 results for: 'neural network optimization'
================================================================================

🔖 Result 1 (similarity: 0.847)
📄 Deep Learning for Scientific Computing (2023)
   Authors: Smith, J., Doe, A.
   Source: ~/Zotero/storage/ABC123/paper.pdf
🧮 Equations: ✓ (Display: 15, Inline: 32)
📝 Content:
Our approach uses stochastic gradient descent with momentum to optimize...
```

**Benefits:**
- Immediate UX improvement
- Easy to test
- Non-breaking change (falls back to current behavior if no title)

### Phase 4: Update Titles Over Time (Medium-High Risk)

**Estimated Effort:** 6-8 hours

This addresses your requirement: "Assume that later we may update titles again."

**Design Considerations:**

1. **Versioning Strategy:**
   - Option A: Overwrite titles (simple, but loses history)
   - Option B: Track metadata version in registry
   - Option C: Store metadata update history in separate table

2. **Source Tracking:**
   Add `metadata_source` and `metadata_updated_date` columns:
   ```sql
   ALTER TABLE documents ADD COLUMN metadata_source TEXT;  -- 'gemma2', 'zotero', 'manual'
   ALTER TABLE documents ADD COLUMN metadata_updated_date TEXT;
   ```

3. **Conflict Resolution:**
   - What if title changes between updates?
   - Trust newer extraction by default?
   - Allow user review of changes?

4. **Re-extraction Trigger:**
   - Command: `rkb extract-metadata --source gemma2 --force-update`
   - Or: `rkb extract-metadata --source zotero` (future integration)
   - Compares new vs old title, shows diff, confirms update

**Recommended Approach:**

```python
# rkb/core/document_registry.py
def update_document_metadata(
    self,
    doc_id: str,
    title: str | None = None,
    authors: list[str] | None = None,
    metadata_source: str | None = None,  # NEW: Track where metadata came from
    force: bool = False,  # NEW: Overwrite even if exists
) -> dict:
    """Update document metadata with conflict detection.

    Returns:
        {
            'updated': True/False,
            'changed_fields': ['title', 'authors'],
            'previous_values': {'title': 'Old Title'},
            'skipped_fields': ['title']  # If force=False and field exists
        }
    """
```

**Benefits:**
- Supports iterative metadata improvement
- Tracks metadata provenance (Gemma2 vs Zotero vs manual)
- Allows re-running extraction as models improve
- Non-destructive updates (can track what changed)

---

## Integration with Zotero (Future)

You mentioned: "Another would be to query my Zotero account. We can add that later."

**Zotero Integration Points:**

1. **Zotero Storage Path Detection (Already Implemented!)**
   - File: `rkb/core/identity.py:49-62`
   - Already extracts Zotero storage IDs from paths like `~/Zotero/storage/ABC123XY/`

2. **Zotero API Client (To Be Implemented)**
   ```python
   # rkb/extractors/metadata/zotero_extractor.py
   from pyzotero import zotero

   class ZoteroExtractor(MetadataExtractor):
       def extract(self, pdf_path: Path) -> DocumentMetadata:
           # Extract Zotero storage ID from path
           storage_id = extract_zotero_id(pdf_path)

           # Query Zotero API
           zot = zotero.Zotero(user_id, 'user', api_key)
           item = zot.item_by_storage_key(storage_id)

           return DocumentMetadata(
               title=item.get('title'),
               authors=item.get('creators'),
               year=item.get('date'),
               journal=item.get('publicationTitle'),
               extractor='zotero'
           )
   ```

3. **Metadata Source Priority**
   - Zotero > DOI/CrossRef > Gemma2 > First Page Parser > PDF Metadata > Filename
   - Rationale: Zotero is manually curated, most trustworthy

---

## Risks and Mitigations

### Risk 1: Missing Source Files

**Problem:** `source_path` may no longer exist (files moved/deleted).

**Mitigation:**
- Check `source_path.exists()` before computing hashes
- Log missing files to separate report
- Skip gracefully with warning
- Consider storing relative paths or multiple path references

### Risk 2: Hash Collisions (MD5 vs SHA-256)

**Problem:** Same file may hash differently if metadata changes.

**Mitigation:**
- PDF content hash should be stable (metadata changes don't affect binary content)
- Use SHA-256 as source of truth
- Treat MD5 as cache key for build_metadata_db.py only

### Risk 3: Encoding Issues (Authors List)

**Problem:** Authors stored as comma-separated string `"Smith,Doe,Lee"`.

**Current Implementation:**
```python
# rkb/core/document_registry.py:126
authors=",".join(document.authors) if document.authors else None
```

**Issue:** Author names with commas will break: `"Smith, Jr., John"`

**Mitigation:**
- Use JSON encoding: `json.dumps(document.authors)`
- Update retrieval: `json.loads(row["authors"])`
- Add migration for existing data

### Risk 4: Large-Scale Updates

**Problem:** Syncing metadata for 10,000+ documents may be slow.

**Mitigation:**
- Add progress bar (use `tqdm`)
- Batch database updates (transaction per 100 docs)
- Support resumable updates (checkpoint after each batch)
- Add `--limit` flag for testing

---

## Recommended Implementation Order

### Week 1: Minimum Viable Title Display
1. ✅ Phase 1: Add `update_document_metadata()` (2-3 hours)
2. ✅ Phase 3: Display titles in search (2-3 hours)
3. ✅ Manual testing with a few documents
**Deliverable:** Search results show titles when manually set

### Week 2: Bulk Metadata Sync
4. ✅ Phase 2: `sync_metadata` command (4-6 hours)
5. ✅ Test with real Zotero library subset
6. ✅ Fix encoding issues if found
**Deliverable:** All existing documents have titles from metadata DB

### Week 3: Future-Proofing
7. ✅ Phase 4: Metadata versioning (6-8 hours)
8. ✅ Add Zotero extractor (optional, 8-10 hours)
9. ✅ Documentation and user guide
**Deliverable:** System supports iterative title updates

---

## Effort Estimation Summary

| Task | Difficulty | Hours | Priority |
|------|------------|-------|----------|
| Add metadata update method | Low | 2-3 | **HIGH** |
| Sync metadata command | Medium | 4-6 | **HIGH** |
| Display titles in search | Low | 2-3 | **HIGH** |
| Metadata versioning | Medium-High | 6-8 | Medium |
| Zotero integration | Medium | 8-10 | Low |
| Testing & documentation | Low-Medium | 4-6 | **HIGH** |
| **Total (MVP)** | | **12-18** | |
| **Total (Full)** | | **26-36** | |

**MVP = Phases 1-3:** Get titles into search results (12-18 hours)
**Full = Phases 1-4 + Zotero:** Support evolving metadata (26-36 hours)

---

## Code Locations Reference

| Component | File | Lines | Status |
|-----------|------|-------|--------|
| Document model | `rkb/core/models.py` | 21-40 | Has title field ✓ |
| Registry schema | `rkb/core/document_registry.py` | 46-61 | Has title column ✓ |
| Document creation | `rkb/core/document_registry.py` | 478-484 | **No title set** ✗ |
| Metadata extraction | `rkb/extractors/metadata/gemma2_extractor.py` | 53-107 | Works, isolated ✓ |
| Metadata storage | `rkb/cli/build_metadata_db.py` | Full file | MD5-keyed JSON ✓ |
| Search display | `rkb/services/search_service.py` | 717-780 | **No titles shown** ✗ |
| Hash (SHA-256) | `rkb/core/identity.py` | 22-32 | Primary ID ✓ |
| Hash (MD5) | `rkb/core/text_processing.py` | hash_file() | Metadata cache ✓ |

---

## Questions for Clarification

1. **Metadata DB Location:** Where is `data/metadata_db.json` typically stored? Is it committed to git or user-specific?

2. **Title Update Policy:** When re-extracting metadata, should we:
   - Always overwrite existing titles?
   - Only fill in missing titles (skip if exists)?
   - Show diff and ask user to confirm changes?

3. **Zotero Priority:** How important is Zotero integration vs improving Gemma2 extraction?

4. **Search UX:** Should search results show:
   - Title only?
   - Title + authors?
   - Title + authors + year + journal?

5. **Multiple Paths:** Some documents may have multiple `source_path` entries (duplicates). Should they all share the same title?

---

## Conclusion

**Bottom Line:** Integrating titles into RAG search is **MEDIUM difficulty** because:

✅ **Easy parts:**
- Infrastructure exists (database columns, metadata extraction)
- Display changes are straightforward
- No algorithmic complexity

⚠️ **Challenging parts:**
- Bridging MD5/SHA-256 hash systems
- Handling missing source files
- Designing for future metadata updates
- Encoding edge cases (author names, special characters)

**Recommended approach:** Start with MVP (Phases 1-3) to get immediate value, then iterate on versioning and Zotero integration based on actual usage patterns.
