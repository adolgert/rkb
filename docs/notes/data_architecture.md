Current Data Architecture Analysis

  Data Flow Pipeline

  1. Source PDFs (data/initial/)
     ↓
  2. Discovery & Metadata (find_recent.py → recent_pdfs.json)
     ↓
  3. Text Extraction (extract.py/robust_extract.py → extracted/*.mmd)
     ↓
  4. Chunking & Embedding (index.py → chroma_db/)
     ↓
  5. Search Interface (search.py)

  Storage Layers

  1. Source Layer (data/initial/)
    - Raw PDF files
    - No versioning or deduplication
    - Metadata: filename, size, modification time
  2. Extraction Layer (nugget/extracted/, nugget/robust_extracted/)
    - Markdown files (.mmd) from Nougat OCR
    - 1:1 mapping with source PDFs
    - Two directories for different extraction strategies
    - No content hashing or duplicate detection
  3. Index Layer (nugget/chroma_db/)
    - Vector embeddings in Chroma
    - SQLite metadata + binary vector storage
    - Chunk-level granularity with limited traceability

  Metadata Structures

  File Discovery (recent_pdfs.json):
  {
    "path": "data/initial/file.pdf",
    "name": "file.pdf",
    "size_mb": 1.23,
    "modified_time": 1759008276,
    "modified_date": "2025-09-27 17:24:36"
  }

  Extraction Logs (extraction_log.json):
  {
    "status": "success/error/skipped",
    "pdf_path": "source path",
    "output_path": "extracted path",
    "message": "status details"
  }

  Chunk Metadata (in Chroma):
  {
    "source_file": "markdown.mmd",
    "pdf_name": "pdf_basename",
    "chunk_index": 0,
    "chunk_length": 1500,
    "has_equations": true,
    "display_eq_count": 2,
    "inline_eq_count": 5,
    "processed_date": "ISO timestamp"
  }

  Critical Architecture Gaps

  1. No Content-Based Identification
    - Files tracked by name/path only
    - No MD5/SHA hashes for deduplication
    - ArXiv version updates (v1→v2→v3) create duplicates
  2. Weak Document Traceability
    - Chunks link to .mmd files, not original PDFs
    - No page number preservation
    - Lost hierarchical structure (chapters/sections)
  3. No Version Management
    - Cannot replace/update documents
    - No deletion cascade (PDF→MMD→chunks)
    - Manual cleanup required for updates
  4. Limited Metadata
    - No paper metadata (title, authors, DOI, ArXiv ID)
    - No extraction quality metrics
    - No inter-document relationships
  5. Fragmented State
    - Multiple JSON logs without central registry
    - Two extraction directories without clear reconciliation
    - No transaction/rollback capability

● How Architecture Would Handle Updates

  Current Behavior for Duplicate/Version Replacement:

  1. Adding newer ArXiv version (e.g., paper_v2.pdf replacing paper_v1.pdf):
    - Both files coexist in data/initial/
    - Both get extracted to separate .mmd files
    - Both get indexed, creating duplicate chunks
    - Search returns results from both versions
    - No way to identify which is newer without filename parsing
  2. Replacing a PDF:
    - Old extraction remains in extracted/
    - Old chunks remain in Chroma database
    - New file creates additional chunks
    - No cascade deletion mechanism
  3. Deleting a PDF:
    - Source file removed from data/initial/
    - Extracted .mmd remains orphaned
    - Chunks remain searchable in Chroma
    - No referential integrity

  Recommended Architecture Improvements

  To support proper versioning and deduplication:

  1. Document Registry (SQLite/JSON):
  {
    "doc_id": "uuid",
    "content_hash": "sha256",
    "arxiv_id": "2506.06542",
    "version": 3,
    "title": "extracted_title",
    "authors": ["list"],
    "source_path": "current_pdf_path",
    "extracted_path": "mmd_path",
    "chunk_ids": ["chunk_1", "chunk_2"],
    "added_date": "timestamp",
    "updated_date": "timestamp"
  }
  2. Content-Based Operations:
    - Hash PDFs on ingestion
    - Detect duplicates before extraction
    - Track ArXiv IDs for version management
    - Link all derivatives to document ID
  3. Cascade Operations:
    - Delete document → remove extraction → delete chunks
    - Update document → re-extract → replace chunks
    - Archive old versions instead of overwriting
  4. Enhanced Chunk Metadata:
  {
    "doc_id": "parent_document_uuid",
    "page_numbers": [3, 4],  # Original PDF pages
    "section_hierarchy": ["2. Methods", "2.1 Algorithm"],
    "extraction_quality": 0.95,
    "version": 2
  }

  This architecture would enable:
  - Automatic deduplication
  - Version tracking for ArXiv papers
  - Clean updates/deletions
  - Document-level search results
  - Provenance tracking from search result to source PDF
