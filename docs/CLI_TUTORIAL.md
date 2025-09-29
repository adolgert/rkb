# RKB CLI Quick Tutorial

This tutorial shows how to use the RKB command-line interface for PDF processing and semantic search with automatic duplicate detection and content-based deduplication.

## Prerequisites

1. **Install RKB**: `pip install -e .`
2. **Ollama running**: Make sure Ollama service is running (`ollama serve`)
3. **PDF files**: Have PDF files in a directory (e.g., `data/initial/`)

## Basic Workflow

### Step 1: Find PDFs

First, scan your directory to see what PDFs are available:

```bash
rkb find --data-dir data/initial --num-files 10
```

This will show you the 10 most recent PDF files in your directory and all subdirectories (recursive search).

### Step 2: Create a Project (Optional)

Organize your documents into a project:

```bash
rkb project create "My Research Project" --description "Testing RKB system" --data-dir data/initial
```

This returns a project ID like `project_1759080878` that you can use in subsequent commands.

### Step 3: Extract Content from PDFs

Extract text and structure from your PDFs:

```bash
rkb extract data/initial/your_file.pdf --max-pages 5 --force-reprocess
```

**New behavior**: The system automatically detects duplicate content using SHA-256 hashes. If you try to extract the same PDF again, it will show "duplicate" status unless you use `--force-reprocess`.

**Currently errors**: The extraction completes successfully but the CLI reports it as failed due to embedding errors. The underlying PDF→MMD conversion works correctly.

### Step 4: Complete Pipeline (Extract + Index)

Run the full pipeline to extract and create embeddings:

```bash
rkb pipeline --data-dir data/initial --num-files 3 --project-name "Test Project" --extractor nougat --embedder chroma --max-pages 5
```

**New behavior**: The pipeline now handles duplicate filenames automatically and recursively searches subdirectories. Multiple files named "Document.pdf" from different sources (like Zotero storage folders) are processed without conflicts. Identical content is automatically detected and linked. Perfect for Zotero storage with its `ABC123/Document.pdf` structure.

**Currently errors**: The pipeline fails during the embedding step with array comparison issues in ChromaDB. The extraction portion works correctly.

### Step 5: Index Existing Extractions

If you have extracted documents, create embeddings for search:

```bash
rkb index --embedder chroma --project-id project_1759080878
```

**Currently errors**: Same embedding issues as the pipeline command.

### Step 6: Search Documents

Once indexed, search your documents:

```bash
rkb search "machine learning transformers"
```

**Currently errors**: No vector database exists due to indexing failures.

Interactive search mode:
```bash
rkb search --interactive
```

### Step 7: Project Management

List your projects:
```bash
rkb project list
```

Show project details:
```bash
rkb project show project_1759080878
```

## Working Alternatives

### Direct Python API (Works Perfectly)

While the CLI has embedding issues, the core extraction works perfectly via Python. The new deduplication system also works transparently:

```python
from rkb.extractors.nougat_extractor import NougatExtractor
from pathlib import Path

# Extract PDF to MMD format
extractor = NougatExtractor(max_pages=10)
result = extractor.extract(Path("data/initial/your_file.pdf"))

# Save the MMD content
with open("output.mmd", "w") as f:
    f.write(result.content)

print(f"Extracted {len(result.content)} characters")
print(f"Status: {result.status}")
print(f"Found equations: {result.chunk_metadata}")
```

### Direct Pipeline Testing

```python
from rkb.pipelines.ingestion_pipeline import IngestionPipeline
from rkb.core.document_registry import DocumentRegistry

pipeline = IngestionPipeline(
    registry=DocumentRegistry(),
    extractor_name='nougat',
    embedder_name='chroma'
)

# First time processing
result1 = pipeline.process_single_document(
    Path("data/initial/your_file.pdf")
)
print(result1)  # Shows successful extraction

# Second time - will detect duplicate
result2 = pipeline.process_single_document(
    Path("data/initial/copy_of_your_file.pdf")  # Same content, different name
)
print(result2)  # Shows "duplicate" status if same content
```

## Current Status Summary

✅ **Working**:
- PDF discovery (`rkb find`)
- Project management (`rkb project`)
- Core PDF→MMD extraction (Python API)
- Text chunking and equation detection
- **NEW**: Automatic duplicate detection and content-based deduplication
- **NEW**: Handling of duplicate filenames (e.g., multiple "Document.pdf")
- **NEW**: UUID-based storage paths for extracted content

❌ **Currently errors**:
- CLI extraction commands (report failures despite successful extraction)
- Complete pipeline (`rkb pipeline`)
- Document indexing (`rkb index`)
- Search functionality (`rkb search`)

## Known Issues

1. **Embedding Collection**: ChromaDB collection creation has array comparison errors
2. **CLI Error Reporting**: CLI marks successful extractions as failed due to embedding issues
3. **Exception Handling**: Fixed collection name mismatch but numpy array issues remain

## Storage Structure (Updated)

The system now uses UUID-based storage for better duplicate handling:

```
rkb_extractions/
├── documents/
│   ├── {doc_id_uuid_1}/
│   │   ├── extracted.mmd
│   │   └── metadata.json
│   └── {doc_id_uuid_2}/
│       ├── extracted.mmd
│       └── metadata.json
```

**Key changes**:
- Each document gets a unique UUID-based directory
- Content is stored by `doc_id` rather than filename
- Multiple source paths can reference the same content
- Eliminates filename collision issues

## Expected Processing Times

- **PDF Extraction**: ~2-3 minutes per PDF (depending on length and pages)
- **Small PDF (6 pages)**: ~107 seconds
- **Embedding Generation**: Currently failing, but should be ~30-60 seconds per document

## Testing Duplicate Detection

### Test 1: Duplicate Filenames (Different Content)

```bash
# Create test structure with same filenames, different content
mkdir -p test_data/zotero1 test_data/zotero2

# Simulate Zotero storage structure
echo "Content of paper 1" > test_data/zotero1/Document.pdf
echo "Content of paper 2" > test_data/zotero2/Document.pdf

# Process both - should succeed without conflicts
rkb extract test_data/zotero1/Document.pdf test_data/zotero2/Document.pdf

# Expected: Both files processed successfully, different doc_ids assigned
```

### Test 2: Identical Content (Different Names/Paths)

```bash
# Create identical content with different names
cp test_data/zotero1/Document.pdf test_data/duplicate_paper.pdf
cp test_data/zotero1/Document.pdf test_data/another_copy.pdf

# Process all three
rkb extract test_data/zotero1/Document.pdf test_data/duplicate_paper.pdf test_data/another_copy.pdf

# Expected: First file processes normally, others show "duplicate" status
```

### Test 3: Force Reprocessing Duplicates

```bash
# Force reprocess a duplicate
rkb extract test_data/duplicate_paper.pdf --force-reprocess

# Expected: File is reprocessed despite being a duplicate
```

### Test 4: Zotero Storage Simulation

```bash
# Simulate real Zotero storage structure
mkdir -p test_zotero/Zotero/storage/{ABC123,XYZ789,DEF456}

# Create realistic Zotero scenario
cp sample1.pdf test_zotero/Zotero/storage/ABC123/Document.pdf
cp sample2.pdf test_zotero/Zotero/storage/XYZ789/Document.pdf
cp sample1.pdf test_zotero/Zotero/storage/DEF456/Paper.pdf  # Duplicate content

# Process the entire directory (now recursively finds PDFs in subdirectories)
rkb pipeline --data-dir test_zotero/Zotero/storage --num-files 10

# Expected:
# - ABC123/Document.pdf: processed successfully
# - XYZ789/Document.pdf: processed successfully (different content)
# - DEF456/Paper.pdf: marked as duplicate of ABC123 version
```

### Test 6: Real Zotero Storage Usage

```bash
# Find recent PDFs in your actual Zotero storage (now works with subdirectories!)
rkb find --data-dir ~/Zotero/storage --num-files 20

# Process recent papers from your Zotero library
rkb pipeline --data-dir ~/Zotero/storage --num-files 10 --project-name "Zotero Papers" --max-pages 15

# The system will:
# - Recursively find all PDFs in Zotero's ABC123/Document.pdf structure
# - Handle duplicate filenames automatically
# - Detect content duplicates across different Zotero folders
# - Create UUID-based storage that doesn't conflict with Zotero's naming
```

### Test 5: Verify Storage Structure

```bash
# After running tests, check the storage structure
ls -la rkb_extractions/documents/

# Expected: UUID-based directories, not filename-based
# Each doc_id directory contains extracted.mmd
```

## Help Commands

- `rkb --help` - Main help
- `rkb extract --help` - Extraction options
- `rkb pipeline --help` - Pipeline options
- `rkb search --help` - Search options
- `rkb project --help` - Project management options