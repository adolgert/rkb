# RKB CLI Quick Tutorial

This tutorial shows how to use the RKB command-line interface for PDF processing and semantic search.

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

This will show you the 10 most recent PDF files in your directory.

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

**Currently errors**: The extraction completes successfully but the CLI reports it as failed due to embedding errors. The underlying PDF→MMD conversion works correctly.

### Step 4: Complete Pipeline (Extract + Index)

Run the full pipeline to extract and create embeddings:

```bash
rkb pipeline --data-dir data/initial --num-files 3 --project-name "Test Project" --extractor nougat --embedder chroma --max-pages 5
```

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

While the CLI has embedding issues, the core extraction works perfectly via Python:

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

result = pipeline.process_single_document(
    Path("data/initial/your_file.pdf"),
    force_reprocess=True
)
print(result)  # Shows successful extraction
```

## Current Status Summary

✅ **Working**:
- PDF discovery (`rkb find`)
- Project management (`rkb project`)
- Core PDF→MMD extraction (Python API)
- Text chunking and equation detection

❌ **Currently errors**:
- CLI extraction commands (report failures despite successful extraction)
- Complete pipeline (`rkb pipeline`)
- Document indexing (`rkb index`)
- Search functionality (`rkb search`)

## Known Issues

1. **Embedding Collection**: ChromaDB collection creation has array comparison errors
2. **CLI Error Reporting**: CLI marks successful extractions as failed due to embedding issues
3. **Exception Handling**: Fixed collection name mismatch but numpy array issues remain

## Expected Processing Times

- **PDF Extraction**: ~2-3 minutes per PDF (depending on length and pages)
- **Small PDF (6 pages)**: ~107 seconds
- **Embedding Generation**: Currently failing, but should be ~30-60 seconds per document

## Help Commands

- `rkb --help` - Main help
- `rkb extract --help` - Extraction options
- `rkb pipeline --help` - Pipeline options
- `rkb search --help` - Search options
- `rkb project --help` - Project management options