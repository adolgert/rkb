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
  2. Extraction Layer (extractions/documents/{doc_id}/)  # ✅ UPDATED
    - UUID-based directory structure for organization
    - extracted.mmd files from Nougat OCR
    - metadata.json for document metadata
    - ✅ Content hashing and duplicate detection implemented
    - ✅ PathResolver for consistent path management
  3. Index Layer (rkb_chroma_db/)
    - Vector embeddings in Chroma
    - SQLite metadata + binary vector storage
    - ✅ Enhanced chunk-level granularity with doc_id traceability

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
    "source_file": "extracted.mmd",  # UUID-based path
    "pdf_name": "original_filename.pdf",
    "doc_id": "document_uuid",  # ✅ IMPLEMENTED - proper document lineage
    "chunk_index": 0,
    "chunk_length": 1500,
    "has_equations": true,
    "display_eq_count": 2,
    "inline_eq_count": 5,
    "processed_date": "ISO timestamp",
    "content_hash": "sha256_hash",  # ✅ IMPLEMENTED - content deduplication
    "source_type": "zotero",  # ✅ IMPLEMENTED - source detection
    "zotero_id": "ABC123"  # ✅ IMPLEMENTED - Zotero reference
  }

  Architecture Improvements (2025-09-29)

  ✅ Content-Based Identification (IMPLEMENTED)
    - SHA-256 content hashing for deduplication
    - DocumentIdentity class for centralized identity management
    - Automatic duplicate detection and linking
    - Support for multiple source paths referencing same content

  ✅ Enhanced Document Traceability (IMPLEMENTED)
    - UUID-based document storage (doc_id)
    - PathResolver for consistent extraction organization
    - Direct linkage from chunks to original documents
    - Proper document lineage preservation

  ✅ Zotero Storage Support (IMPLEMENTED)
    - Read-only access to ~/Zotero/storage structure
    - Handles 6000+ files with duplicate filenames
    - Source type detection (zotero/dropbox/local)
    - Zotero ID extraction for traceability

  ✅ Database Schema Updates (IMPLEMENTED)
    - Removed UNIQUE constraint on source_path
    - Enhanced DocumentRegistry with content hash methods
    - Support for multiple source references per document
    - Proper deduplication logic in process_new_document()

  Remaining Gaps
  1. Limited Metadata Enhancement
    - Paper metadata extraction (title, authors, DOI, ArXiv ID)
    - Extraction quality metrics
    - Inter-document relationships
  2. Advanced Version Management
    - Document replacement workflows
    - Deletion cascade operations
    - Transaction/rollback capability
  3. Multiple Source References
    - Track all source paths that reference same document
    - Source synchronization monitoring

● How Architecture Would Handle Updates

  Current Behavior for Duplicate/Version Replacement:

  1. Adding duplicate documents:
    - Both files coexist in data/initial/
    - Both get extracted to separate .mmd files
    - Both get indexed, creating duplicate chunks
    - Search returns results from both versions
    - No content-based deduplication mechanism
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
    - Track ArXiv IDs for paper identification
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
  - Clean updates/deletions
  - Document-level search results
  - Provenance tracking from search result to source PDF

## ✅ Implemented Components (2025-09-29)

### Core Infrastructure

#### DocumentIdentity (rkb/core/identity.py)
- Manages document identity, content hashing, and storage paths
- SHA-256 content hash calculation for deduplication
- Source type detection (zotero/dropbox/local)
- Zotero ID extraction from storage paths
- UUID generation for consistent document IDs

#### PathResolver (rkb/core/paths.py)
- Centralized path generation for all RKB storage
- UUID-based directory structure: `extractions/documents/{doc_id}/`
- Consistent naming: `extracted.mmd`, `metadata.json`
- Directory creation and management utilities

### Database Enhancements

#### DocumentRegistry Updates
- **Enhanced Methods:**
  - `find_by_content_hash()` - Locate documents by SHA-256 hash
  - `process_new_document()` - Content-based deduplication workflow
  - `add_document_reference()` - Link multiple sources to same content
  - `update_document_content_hash()` - Content hash management
  - `get_all_documents()` - Complete document retrieval

- **Schema Changes:**
  - Removed UNIQUE constraint on `source_path`
  - Proper `project_id` handling in all methods
  - Enhanced error handling for UUID collisions

### Pipeline Integration

#### NougatExtractor Updates
- Accepts optional `doc_id` parameter for consistent naming
- Uses PathResolver for UUID-based extraction paths
- Creates `extractions/documents/{doc_id}/extracted.mmd` structure
- Maintains backward compatibility with existing interface

#### IngestionPipeline Updates
- Uses `process_new_document()` for automatic deduplication
- Status-aware processing (checks INDEXED before duplicate detection)
- Passes doc_id to extractor for consistent file organization
- Enhanced logging with doc_id information

### Testing Coverage

#### Unit Tests (29 tests)
- DocumentIdentity: Content hashing, source detection, path generation
- PathResolver: Directory management, path consistency
- DocumentRegistry: Deduplication logic, content hash operations
- NougatExtractor: doc_id integration, path structure
- IngestionPipeline: Duplicate handling, status management

#### Integration Tests (7 tests)
- Zotero workflow simulation with realistic directory structure
- Duplicate filename handling across different sources
- Content deduplication with identical files
- Read-only source preservation verification
- End-to-end pipeline testing with mocked components

### Zotero Support Features

#### Source Detection
```python
identity = DocumentIdentity(Path("/home/user/Zotero/storage/ABC123/Document.pdf"))
assert identity.source_type == "zotero"
assert identity.zotero_id == "ABC123"
```

#### Duplicate Filename Handling
- Multiple `Document.pdf` files from different Zotero entries
- Content-based deduplication prevents duplicate processing
- Maintains traceability to original source locations
- Read-only access ensures source directory integrity

#### Performance Characteristics
- Supports 6000+ files in Zotero storage
- SHA-256 hashing for reliable content identification
- UUID-based organization prevents filename conflicts
- Efficient database indexing on content_hash and doc_id

### Usage Examples

#### Processing Zotero Storage
```python
from rkb.pipelines.ingestion_pipeline import IngestionPipeline

pipeline = IngestionPipeline(project_id="research_papers")

# Process entire Zotero storage
zotero_files = Path("~/Zotero/storage").rglob("*.pdf")
for pdf_file in zotero_files:
    result = pipeline.process_single_document(pdf_file)
    print(f"Status: {result['status']}, doc_id: {result['doc_id']}")
```

#### Manual Document Processing
```python
from rkb.core.document_registry import DocumentRegistry

registry = DocumentRegistry("rkb_documents.db")

# Process with automatic deduplication
doc, is_new = registry.process_new_document(
    Path("/path/to/paper.pdf"),
    project_id="my_project"
)

if is_new:
    print(f"New document: {doc.doc_id}")
else:
    print(f"Duplicate detected: {doc.content_hash}")
```
