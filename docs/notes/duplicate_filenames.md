# Duplicate Filenames and Zotero Storage Implementation Plan

## Problem Statement

### Current Limitations
1. **Zotero Storage**: 6000+ files in `~/Zotero/storage` with unique directory names (e.g., `ABC123/Document.pdf`)
2. **Filename Collisions**: Multiple files named "Document.pdf" from different sources
3. **Read-Only Sources**: Cannot write to Zotero storage directory
4. **Multiple Input Types**: Zotero, Dropbox, local directories all need support
5. **Deduplication**: Same paper from different sources should be detected

### Requirements
- Never write to source directories (especially Zotero)
- Handle identical filenames from different sources
- Support content-based deduplication
- Maintain traceability from search results to source files
- Work with existing doc_id (UUID) system

## Solution Architecture

### Chosen Approach: UUID-based Storage with Content Hashing

**Core Principles:**
1. Use `doc_id` (UUID) for all internal storage paths
2. Use SHA-256 content hash for deduplication detection
3. Store full source metadata in database
4. Create centralized identity and path management

**Storage Structure:**
```
extractions/
├── documents/
│   ├── {doc_id_1}/
│   │   ├── extracted.mmd
│   │   └── metadata.json
│   └── {doc_id_2}/
│       ├── extracted.mmd
│       └── metadata.json
```

**Database Changes:**
- Remove UNIQUE constraint on `source_path`
- Add content-based deduplication via `content_hash`
- Support multiple documents referencing same physical file

## Implementation Steps

### Phase 1: Core Infrastructure

#### Step 1.1: Create DocumentIdentity Class
**File:** `rkb/core/identity.py`

```python
"""Document identity and path management."""

import hashlib
import uuid
from pathlib import Path
from typing import Optional

class DocumentIdentity:
    """Manages document identity, content hashing, and storage paths."""

    def __init__(self, source_path: Path, content_hash: Optional[str] = None):
        self.doc_id = str(uuid.uuid4())
        self.source_path = source_path.resolve()
        self.content_hash = content_hash or self._calculate_content_hash()

    def _calculate_content_hash(self) -> str:
        """Calculate SHA-256 hash of file content."""
        sha256_hash = hashlib.sha256()
        with open(self.source_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    @property
    def source_type(self) -> str:
        """Detect source type from path."""
        path_str = str(self.source_path)
        if "Zotero/storage" in path_str:
            return "zotero"
        elif "Dropbox" in path_str:
            return "dropbox"
        else:
            return "local"

    @property
    def zotero_id(self) -> Optional[str]:
        """Extract Zotero storage ID if applicable."""
        if self.source_type == "zotero":
            parts = self.source_path.parts
            try:
                storage_idx = parts.index("storage")
                return parts[storage_idx + 1]
            except (ValueError, IndexError):
                return None
        return None

    def get_extraction_path(self, base_dir: Path = Path("extractions")) -> Path:
        """Get path for extracted content."""
        return base_dir / "documents" / self.doc_id / "extracted.mmd"

    def get_metadata_path(self, base_dir: Path = Path("extractions")) -> Path:
        """Get path for document metadata."""
        return base_dir / "documents" / self.doc_id / "metadata.json"
```

**Checkpoint 1.1:**
- [ ] Create the file and ensure imports work
- [ ] Test DocumentIdentity creation with a sample PDF
- [ ] Verify content hash calculation works
- [ ] Test path generation methods

#### Step 1.2: Create PathResolver Class
**File:** `rkb/core/paths.py`

```python
"""Centralized path resolution for all RKB storage."""

from pathlib import Path

class PathResolver:
    """Static methods for consistent path generation."""

    @staticmethod
    def get_extraction_dir(doc_id: str, base_dir: Path = Path("extractions")) -> Path:
        """Get document extraction directory."""
        return base_dir / "documents" / doc_id

    @staticmethod
    def get_extraction_path(doc_id: str, base_dir: Path = Path("extractions")) -> Path:
        """Get path for extracted content file."""
        return PathResolver.get_extraction_dir(doc_id, base_dir) / "extracted.mmd"

    @staticmethod
    def get_metadata_path(doc_id: str, base_dir: Path = Path("extractions")) -> Path:
        """Get path for document metadata file."""
        return PathResolver.get_extraction_dir(doc_id, base_dir) / "metadata.json"

    @staticmethod
    def ensure_extraction_dir(doc_id: str, base_dir: Path = Path("extractions")) -> Path:
        """Create extraction directory if it doesn't exist."""
        extract_dir = PathResolver.get_extraction_dir(doc_id, base_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)
        return extract_dir
```

**Checkpoint 1.2:**
- [ ] Create file and test all path generation methods
- [ ] Verify directory creation works
- [ ] Test with various doc_id formats

### Phase 2: Database Updates

#### Step 2.1: Add Content Hash Support to DocumentRegistry
**File:** `rkb/core/document_registry.py`

Add these methods to the DocumentRegistry class:

```python
def find_by_content_hash(self, content_hash: str) -> Document | None:
    """Find document by content hash."""
    with sqlite3.connect(self.db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT * FROM documents WHERE content_hash = ?
        """, (content_hash,))
        row = cursor.fetchone()

        if row:
            return Document(
                doc_id=row['doc_id'],
                source_path=Path(row['source_path']) if row['source_path'] else None,
                content_hash=row['content_hash'],
                title=row['title'],
                authors=row['authors'].split(',') if row['authors'] else [],
                arxiv_id=row['arxiv_id'],
                doi=row['doi'],
                version=row['version'],
                status=DocumentStatus(row['status']),
                added_date=datetime.fromisoformat(row['added_date']),
                project_id=row['project_id'],
            )
        return None

def add_document_reference(self, existing_doc: Document, new_source_path: Path) -> Document:
    """Add a new source path reference to existing document."""
    # For now, just update the existing document's source_path if needed
    # In future, could maintain multiple source references
    print(f"📋 Linking duplicate: {new_source_path} -> {existing_doc.doc_id}")
    return existing_doc

def process_new_document(self, source_path: Path, project_id: str | None = None) -> tuple[Document, bool]:
    """Process new document with deduplication.

    Returns:
        (Document, is_new) - Document object and whether it was newly created
    """
    from rkb.core.identity import DocumentIdentity

    # Create identity object
    doc_identity = DocumentIdentity(source_path)

    # Check for existing document with same content
    existing_doc = self.find_by_content_hash(doc_identity.content_hash)
    if existing_doc:
        # Link to existing document
        linked_doc = self.add_document_reference(existing_doc, source_path)
        return linked_doc, False

    # Create new document
    document = Document(
        doc_id=doc_identity.doc_id,
        source_path=source_path,
        content_hash=doc_identity.content_hash,
        status=DocumentStatus.PENDING,
        project_id=project_id,
    )

    # Add to registry
    success = self.add_document(document)
    return document, success
```

**Checkpoint 2.1:**
- [ ] Add methods to DocumentRegistry
- [ ] Test content hash lookup with sample documents
- [ ] Verify deduplication logic works
- [ ] Test that duplicate detection returns existing documents

#### Step 2.2: Remove Source Path Unique Constraint
**File:** `rkb/core/document_registry.py`

In the `_init_database` method, modify the documents table creation:

```python
# OLD:
#     UNIQUE(source_path)

# NEW: (remove the UNIQUE constraint)
# No unique constraint on source_path - multiple docs can reference same file
```

Also update the `add_document` method to handle the case where multiple documents might have the same source_path:

```python
def add_document(self, document: Document) -> bool:
    """Add a document to the registry."""
    try:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO documents (
                    doc_id, source_path, content_hash, title, authors,
                    arxiv_id, doi, version, status, added_date, updated_date, project_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                document.doc_id,
                str(document.source_path) if document.source_path else None,
                document.content_hash,
                document.title,
                ",".join(document.authors) if document.authors else None,
                document.arxiv_id,
                document.doi,
                document.version,
                document.status.value,
                document.added_date.isoformat(),
                datetime.now().isoformat(),
                getattr(document, 'project_id', None),
            ))
            return True
    except sqlite3.IntegrityError as e:
        # Handle case where doc_id already exists (should be rare with UUIDs)
        print(f"Document ID collision: {e}")
        return False
```

**Checkpoint 2.2:**
- [ ] Update database schema creation
- [ ] Test adding multiple documents with same source_path
- [ ] Verify no unique constraint errors occur
- [ ] Test that different doc_ids can reference same file

### Phase 3: Update Extractors

#### Step 3.1: Update NougatExtractor
**File:** `rkb/extractors/nougat_extractor.py`

Update the extract method to use DocumentIdentity:

```python
def extract(self, source_path: Path, doc_id: str | None = None) -> ExtractionResult:
    """Extract text from PDF using chunked Nougat processing.

    Args:
        source_path: Path to the PDF file
        doc_id: Document ID for consistent output naming

    Returns:
        ExtractionResult with extracted content and metadata
    """
    from rkb.core.paths import PathResolver

    source_path = Path(source_path)
    if not source_path.exists():
        return ExtractionResult(
            doc_id=doc_id or str(source_path),
            status=ExtractionStatus.FAILED,
            error_message=f"File not found: {source_path}",
        )

    # Use provided doc_id or generate one
    if not doc_id:
        doc_id = str(uuid.uuid4())

    extraction_id = f"{doc_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    try:
        # Process PDF in chunks
        chunks_result = self._extract_pdf_chunks(source_path, extraction_id)

        if not chunks_result["content"]:
            return ExtractionResult(
                doc_id=doc_id,
                extraction_id=extraction_id,
                status=ExtractionStatus.FAILED,
                error_message="No content extracted from any chunks",
            )

        # Clean and process the extracted text
        cleaned_content = clean_extracted_text(chunks_result["content"])

        # Use PathResolver for consistent output location
        extraction_path = PathResolver.get_extraction_path(doc_id, self.output_dir)

        # Ensure directory exists
        PathResolver.ensure_extraction_dir(doc_id, self.output_dir)

        # Save extraction to file
        extraction_path.write_text(cleaned_content, encoding="utf-8")

        return ExtractionResult(
            doc_id=doc_id,
            extraction_id=extraction_id,
            extraction_path=extraction_path,
            content=cleaned_content,
            # ... rest of the result fields
        )
```

**Checkpoint 3.1:**
- [ ] Update NougatExtractor to accept doc_id parameter
- [ ] Test extraction with provided doc_id
- [ ] Verify extraction files are saved to correct doc_id-based paths
- [ ] Test that multiple documents can be extracted without conflicts

### Phase 4: Update Pipeline Integration

#### Step 4.1: Update IngestionPipeline
**File:** `rkb/pipelines/ingestion_pipeline.py`

Update the `process_single_document` method:

```python
def process_single_document(
    self,
    source_path: Path,
    force_reprocess: bool = False,
    max_chunk_size: int = 2000,
) -> dict[str, Any]:
    """Process a single document through the complete pipeline."""
    source_path = Path(source_path).resolve()

    # Check if document already exists using the new method
    document, is_new = self.registry.process_new_document(source_path, self.project_id)

    if not is_new and not force_reprocess:
        return {
            "status": "duplicate",
            "message": f"Document already exists with content hash",
            "source_path": str(source_path),
            "doc_id": document.doc_id,
            "content_hash": document.content_hash,
        }

    if document.status == DocumentStatus.INDEXED and not force_reprocess:
        return {
            "status": "skipped",
            "message": "Document already fully processed",
            "source_path": str(source_path),
            "doc_id": document.doc_id,
        }

    start_time = time.time()

    try:
        print(f"🔄 Processing: {source_path.name} (doc_id: {document.doc_id[:8]}...)")

        # Update document status
        self.registry.update_document_status(document.doc_id, DocumentStatus.EXTRACTING)

        # Extract content - pass doc_id for consistent naming
        extraction_result = self.extractor.extract(source_path, document.doc_id)

        # Set document ID in extraction result
        extraction_result.doc_id = document.doc_id

        # Continue with rest of processing...
```

**Checkpoint 4.1:**
- [ ] Update pipeline to use new document processing method
- [ ] Test with duplicate files (same content, different paths)
- [ ] Verify deduplication works correctly
- [ ] Test that forced reprocessing still works

### Phase 5: Testing and Validation

#### Step 5.1: Create Test Cases
**File:** `tests/unit/test_core/test_identity.py`

```python
"""Tests for DocumentIdentity and PathResolver."""

import tempfile
from pathlib import Path
import pytest

from rkb.core.identity import DocumentIdentity
from rkb.core.paths import PathResolver


class TestDocumentIdentity:
    """Test DocumentIdentity functionality."""

    def test_content_hash_calculation(self):
        """Test that content hash is calculated correctly."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pdf', delete=False) as f:
            f.write("test content")
            f.flush()

            identity = DocumentIdentity(Path(f.name))
            assert len(identity.content_hash) == 64  # SHA-256 hex length
            assert identity.content_hash.isalnum()

    def test_duplicate_content_same_hash(self):
        """Test that identical content produces same hash."""
        content = "identical test content"

        with tempfile.NamedTemporaryFile(mode='w', suffix='.pdf', delete=False) as f1:
            f1.write(content)
            f1.flush()

            with tempfile.NamedTemporaryFile(mode='w', suffix='.pdf', delete=False) as f2:
                f2.write(content)
                f2.flush()

                identity1 = DocumentIdentity(Path(f1.name))
                identity2 = DocumentIdentity(Path(f2.name))

                assert identity1.content_hash == identity2.content_hash
                assert identity1.doc_id != identity2.doc_id  # Different doc_ids

    def test_zotero_source_detection(self):
        """Test Zotero source type detection."""
        zotero_path = Path("/home/user/Zotero/storage/ABC123/Document.pdf")
        identity = DocumentIdentity.__new__(DocumentIdentity)  # Skip __init__ for test
        identity.source_path = zotero_path

        assert identity.source_type == "zotero"
        assert identity.zotero_id == "ABC123"

    def test_path_generation(self):
        """Test extraction path generation."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pdf', delete=False) as f:
            f.write("test")
            f.flush()

            identity = DocumentIdentity(Path(f.name))
            extraction_path = identity.get_extraction_path()

            assert "documents" in str(extraction_path)
            assert identity.doc_id in str(extraction_path)
            assert extraction_path.suffix == ".mmd"


class TestPathResolver:
    """Test PathResolver functionality."""

    def test_path_consistency(self):
        """Test that paths are generated consistently."""
        doc_id = "test-doc-id-123"

        path1 = PathResolver.get_extraction_path(doc_id)
        path2 = PathResolver.get_extraction_path(doc_id)

        assert path1 == path2
        assert doc_id in str(path1)

    def test_directory_creation(self):
        """Test directory creation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            doc_id = "test-doc-id-456"
            base_path = Path(temp_dir)

            created_dir = PathResolver.ensure_extraction_dir(doc_id, base_path)

            assert created_dir.exists()
            assert created_dir.is_dir()
            assert doc_id in str(created_dir)
```

**Checkpoint 5.1:**
- [ ] Create comprehensive test suite
- [ ] Test content hash calculation
- [ ] Test deduplication logic
- [ ] Test path generation
- [ ] All tests pass

#### Step 5.2: Integration Testing

Create test that simulates the full Zotero workflow:

**File:** `tests/integration/test_zotero_workflow.py`

```python
"""Integration test for Zotero storage workflow."""

import tempfile
import shutil
from pathlib import Path
import pytest

from rkb.core.document_registry import DocumentRegistry
from rkb.pipelines.ingestion_pipeline import IngestionPipeline


class TestZoteroWorkflow:
    """Test full workflow with Zotero-like structure."""

    @pytest.fixture
    def zotero_structure(self):
        """Create mock Zotero storage structure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)

            # Create Zotero-like structure
            storage_dir = base_dir / "Zotero" / "storage"

            # Create multiple papers with same filename
            (storage_dir / "ABC123").mkdir(parents=True)
            (storage_dir / "ABC123" / "Document.pdf").write_bytes(b"Content of paper 1")

            (storage_dir / "XYZ789").mkdir(parents=True)
            (storage_dir / "XYZ789" / "Document.pdf").write_bytes(b"Content of paper 2")

            # Create identical content in different locations
            (storage_dir / "DEF456").mkdir(parents=True)
            (storage_dir / "DEF456" / "Paper.pdf").write_bytes(b"Content of paper 1")  # Duplicate

            yield storage_dir

    def test_duplicate_filename_handling(self, zotero_structure):
        """Test that duplicate filenames are handled correctly."""
        with tempfile.TemporaryDirectory() as db_dir:
            registry = DocumentRegistry(Path(db_dir) / "test.db")

            # Process both Document.pdf files
            doc1_path = zotero_structure / "ABC123" / "Document.pdf"
            doc2_path = zotero_structure / "XYZ789" / "Document.pdf"

            doc1, is_new1 = registry.process_new_document(doc1_path)
            doc2, is_new2 = registry.process_new_document(doc2_path)

            # Both should be processed as new (different content)
            assert is_new1
            assert is_new2
            assert doc1.doc_id != doc2.doc_id
            assert doc1.content_hash != doc2.content_hash

    def test_content_deduplication(self, zotero_structure):
        """Test that identical content is deduplicated."""
        with tempfile.TemporaryDirectory() as db_dir:
            registry = DocumentRegistry(Path(db_dir) / "test.db")

            # Process original and duplicate
            original_path = zotero_structure / "ABC123" / "Document.pdf"
            duplicate_path = zotero_structure / "DEF456" / "Paper.pdf"

            doc1, is_new1 = registry.process_new_document(original_path)
            doc2, is_new2 = registry.process_new_document(duplicate_path)

            # First should be new, second should be duplicate
            assert is_new1
            assert not is_new2
            assert doc1.doc_id == doc2.doc_id  # Same document
            assert doc1.content_hash == doc2.content_hash

    def test_readonly_source_preservation(self, zotero_structure):
        """Test that source directories are never modified."""
        # Get initial state
        initial_files = list(zotero_structure.rglob("*"))
        initial_content = {}
        for f in initial_files:
            if f.is_file():
                initial_content[f] = f.read_bytes()

        # Process documents
        with tempfile.TemporaryDirectory() as db_dir:
            registry = DocumentRegistry(Path(db_dir) / "test.db")

            for pdf_file in zotero_structure.rglob("*.pdf"):
                registry.process_new_document(pdf_file)

        # Verify source unchanged
        final_files = list(zotero_structure.rglob("*"))
        assert len(final_files) == len(initial_files)

        for f in initial_files:
            if f.is_file():
                assert f.read_bytes() == initial_content[f]
```

**Checkpoint 5.2:**
- [ ] Create integration tests
- [ ] Test Zotero-like directory structures
- [ ] Verify deduplication works end-to-end
- [ ] Confirm source directories are never modified
- [ ] All integration tests pass

### Phase 6: Code Quality and Documentation

#### Step 6.1: Run Code Quality Checks

```bash
# Check import structure
import-linter --config pyproject.toml

# Check code formatting and quality
ruff check --fix .
ruff format .

# Run type checking (if mypy is configured)
mypy rkb/
```

**Checkpoint 6.1:**
- [ ] Import-linter passes (no layer violations)
- [ ] Ruff checks pass with no errors
- [ ] Code is properly formatted
- [ ] Type hints are correct

#### Step 6.2: Update Documentation

Update the following files:

**File:** `docs/notes/data_architecture.md`
- Add section on content-based deduplication
- Update chunk metadata to show doc_id linkage
- Remove references to path-based identification as a gap

**File:** `README.md` (if exists)
- Add information about Zotero support
- Document duplicate handling capabilities

**Checkpoint 6.2:**
- [ ] Documentation updated
- [ ] Examples added for Zotero usage
- [ ] Architecture notes reflect new design

### Phase 7: Migration and Deployment

#### Step 7.1: Database Migration

For existing installations, create a migration script:

**File:** `scripts/migrate_content_hash.py`

```python
"""Migrate existing documents to include content hashes."""

import sys
from pathlib import Path
from rkb.core.document_registry import DocumentRegistry
from rkb.core.identity import DocumentIdentity

def migrate_existing_documents(db_path: Path):
    """Add content hashes to existing documents."""
    registry = DocumentRegistry(db_path)

    # Get all documents without content hashes
    documents = registry.get_all_documents()  # You'll need to implement this

    for doc in documents:
        if not doc.content_hash and doc.source_path and doc.source_path.exists():
            print(f"Updating content hash for {doc.source_path.name}")

            # Calculate content hash
            identity = DocumentIdentity(doc.source_path)
            doc.content_hash = identity.content_hash

            # Update in database
            registry.update_document_content_hash(doc.doc_id, doc.content_hash)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python migrate_content_hash.py <db_path>")
        sys.exit(1)

    db_path = Path(sys.argv[1])
    migrate_existing_documents(db_path)
    print("Migration complete!")
```

**Checkpoint 7.1:**
- [ ] Migration script created
- [ ] Test migration on copy of existing database
- [ ] Verify all documents get content hashes
- [ ] No data loss during migration

#### Step 7.2: End-to-End Validation

Create a comprehensive test with real Zotero data:

1. **Setup Test Environment:**
   ```bash
   # Create test directory structure
   mkdir -p test_zotero/Zotero/storage/{ABC123,XYZ789,DEF456}

   # Add test PDFs (you can use any small PDF files)
   cp sample1.pdf test_zotero/Zotero/storage/ABC123/Document.pdf
   cp sample2.pdf test_zotero/Zotero/storage/XYZ789/Document.pdf
   cp sample1.pdf test_zotero/Zotero/storage/DEF456/Paper.pdf  # Duplicate content
   ```

2. **Run Full Pipeline:**
   ```bash
   # Process the test Zotero directory
   rkb pipeline --data-dir test_zotero/Zotero/storage --project-id test_project
   ```

3. **Verify Results:**
   ```bash
   # Check that duplicates were detected
   rkb search "test query" --project-id test_project

   # Verify extraction files are properly organized
   ls -la extractions/documents/
   ```

**Checkpoint 7.2:**
- [ ] End-to-end test passes
- [ ] Duplicate detection works in real scenario
- [ ] Search results include proper doc_id lineage
- [ ] Extraction files are organized by doc_id
- [ ] No errors in processing

## Success Criteria

Upon completion, the system should:

1. **✅ Handle Duplicate Filenames:** Multiple "Document.pdf" files from different sources are processed without conflicts
2. **✅ Support Zotero Storage:** Can process 6000+ files from `~/Zotero/storage` without writing to that directory
3. **✅ Detect Content Duplicates:** Same paper from different sources is detected and linked
4. **✅ Maintain Traceability:** Search results can be traced back to original source files via doc_id
5. **✅ Preserve Data Integrity:** All existing functionality continues to work
6. **✅ Pass Quality Checks:** Import-linter and ruff checks pass
7. **✅ Complete Test Coverage:** All new functionality is tested

## Rollback Plan

If issues arise during implementation:

1. **Database:** Keep backup of database before migration
2. **Code Changes:** Use git to revert to previous working state
3. **Extraction Files:** Old extraction files remain in place and functional
4. **Search:** Existing search functionality is preserved through doc_id system

## Future Enhancements

Once basic functionality is working:

1. **Multiple Source References:** Track all source paths that reference the same document
2. **Zotero Metadata Integration:** Extract Zotero item metadata from `.bib` files
3. **Conflict Resolution UI:** Interface for handling ambiguous duplicates
4. **Source Synchronization:** Monitor source directories for changes
5. **Advanced Deduplication:** Fuzzy matching for near-duplicates (different PDF versions)

---

*Implementation Date: [To be filled when starting]*
*Completion Date: [To be filled when finished]*
*Tested By: [To be filled]*