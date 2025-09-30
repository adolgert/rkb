Data Architecture: Project-Based Design

  Data Flow Pipeline

  1. Source PDFs (data/initial/)
     ↓
  2. Project Creation (projects/{project_name}/)
     ↓
  3. Text Extraction → extractions.db (per project)
     ↓
  4. Experiment Creation (projects/{project}/experiments/{exp_name}/)
     ↓
  5. Chunking & Embedding → experiment.db + chroma_db/ (per experiment)
     ↓
  6. Search Interface (search.py)

  Storage Layers

  1. Source Layer (data/initial/)
    - Raw PDF files
    - Read-only, never modified
    - Metadata: filename, size, modification time

  2. Project Layer (projects/{project_name}/)
    - Self-contained extraction database (extractions.db)
    - Documents table: doc_id, content_hash, source_path, metadata
    - Extractions table: extraction_id, doc_id, content (markdown), page_count
    - Tied to specific extractor version (e.g., nougat:0.1.17)
    - Immutable once created (upgrading extractor = new project)
    - Config file (config.yaml) with extractor version and settings

  3. Experiment Layer (projects/{project}/experiments/{exp_name}/)
    - Experiment-specific database (experiment.db)
    - Chunks table: chunk_id, extraction_id, content, page_numbers
    - Config table: chunking and embedding parameters
    - Vector database (chroma_db/) with embeddings
    - Ephemeral: can be deleted and rebuilt from project extractions

  Metadata Structures

  Project Config (projects/{project}/config.yaml):
  {
    "project_name": "Nougat v1 Extraction",
    "extractor": {
      "name": "nougat",
      "version": "0.1.17"
    },
    "created_date": "2025-09-29T10:00:00Z",
    "description": "Initial extraction with Nougat v0.1.17"
  }

  Document Metadata (in extractions.db):
  {
    "doc_id": "uuid",
    "content_hash": "sha256",
    "source_path": "/path/to/file.pdf",
    "arxiv_id": "2506.06542",
    "doi": "10.1234/example",
    "title": "extracted_title",
    "authors": ["Author 1", "Author 2"],
    "added_date": "ISO timestamp"
  }

  Chunk Metadata (in experiments/{exp_name}/experiment.db):
  {
    "chunk_id": "uuid",
    "extraction_id": "parent_extraction_uuid",
    "doc_id": "document_uuid",
    "content": "chunk text content",
    "page_numbers": [3, 4],  # ✅ CRITICAL - must be tracked
    "chunk_index": 0,
    "chunk_length": 1500,
    "has_equations": true,
    "display_eq_count": 2,
    "inline_eq_count": 5,
    "created_date": "ISO timestamp"
  }

  Architecture Design (2025-09-29 Update)

  ✅ Project-Based Isolation
    - Each project is self-contained directory
    - Tied to specific extractor version
    - Upgrading extractor = create new project
    - No versioning complexity within single database

  ✅ Experiment Flexibility
    - Multiple experiments per project
    - Each experiment has own chunking/embedding params
    - Experiments are ephemeral (can delete and rebuild)
    - Project extractions are immutable (expensive to recreate)

  ✅ Content-Based Identification (IMPLEMENTED)
    - SHA-256 content hashing for deduplication
    - DocumentIdentity class for centralized identity management
    - Automatic duplicate detection within each project
    - Support for multiple source paths referencing same content

  ✅ Simplified Operations
    - Delete project: `rm -rf projects/{project_name}/`
    - Delete experiment: `rm -rf projects/{project}/experiments/{exp_name}/`
    - No cascade deletion logic needed
    - File system provides referential integrity

  How Architecture Handles Updates

  1. Upgrading Extractor Version:
    - Old project (projects/nougat_v1/) remains unchanged
    - Create new project directory (projects/nougat_v2/)
    - Run extraction pipeline on all PDFs into new project
    - Old project stays searchable during week-long re-extraction
    - When ready: switch default project, optionally delete old one

  2. Experimenting with Chunking:
    - Within existing project, create new experiment
    - Example: projects/nougat_v1/experiments/large_chunks/
    - Rebuild chunks from existing extractions (fast, minutes not hours)
    - Compare experiments side-by-side
    - Delete failed experiments: rm -rf experiments/failed_exp/

  3. Deleting Documents:
    - Remove from project's extractions.db
    - Experiments automatically exclude deleted docs
    - Or: start fresh project without unwanted documents

  4. Adding New Documents:
    - Extract into existing project
    - All experiments within project can access new extractions
    - Rebuild experiments to include new documents

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
