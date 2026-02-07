# Data Migration Guide: Nugget → RKB

This guide helps you migrate from the nugget prototype to the new RKB system.

## Migration Strategy

**Important**: The RKB system does not automatically migrate existing nugget data. Instead, you'll recreate your document corpus using the new system, which ensures data consistency and takes advantage of improvements in the processing pipeline.

## Before You Start

### Prerequisites
1. **Install RKB**: Ensure you have RKB installed with `pip install -e .`
2. **Ollama Running**: Make sure Ollama service is running (`ollama serve`)
3. **Backup Existing Data**: Keep your `nugget/` directory as backup
4. **Identify Source PDFs**: Note the location of your original PDF files

### Understanding the Differences

| Nugget | RKB | Notes |
|--------|-----|-------|
| `nugget/chroma_db/` | `rkb_chroma_db/` | New vector database location |
| No document tracking | `rkb_documents.db` | SQLite registry tracks all documents |
| Individual scripts | `rkb` CLI commands | Unified command interface |
| No project organization | Project-based organization | Optional but recommended |

## Migration Process

### Step 1: Create a New Project (Recommended)

```bash
# Create a project for your migrated documents
rkb project create "Migrated Research Papers" \
  --description "Documents migrated from nugget prototype" \
  --data-dir "/path/to/your/pdfs"

# Note the project ID returned for use in next steps
```

### Step 2: Process Your Documents

#### Option A: Complete Pipeline (Recommended)
Process all documents in one command:

```bash
# Replace with your actual data directory and preferences
rkb pipeline \
  --data-dir "/path/to/your/pdfs" \
  --num-files 50 \
  --project-name "Migrated Research" \
  --extractor nougat \
  --embedder chroma \
  --max-pages 15
```

#### Option B: Step-by-Step Processing
For more control, run each step separately:

```bash
# 1. Find recent PDFs
rkb find --data-dir "/path/to/your/pdfs" --num-files 50 --project-id PROJECT_ID

# 2. Extract content (replace with actual PDF paths)
rkb extract file1.pdf file2.pdf file3.pdf --project-id PROJECT_ID

# 3. Create embeddings and index
rkb index --embedder chroma --project-id PROJECT_ID
```

### Step 3: Verify Migration

#### Test Search Functionality
```bash
# Test search with a query you used before
rkb search "your typical search query"

# Or use interactive mode
rkb search --interactive
```

#### Check Project Status
```bash
# List all projects
rkb project list

# Show detailed project statistics
rkb project show PROJECT_ID
```

#### Compare Database Statistics
```bash
# Show new database statistics
rkb search --stats
```

## Expected Processing Times

Based on nugget performance benchmarks:

- **PDF Extraction**: ~2-3 minutes per PDF (depending on length)
- **Embedding Generation**: ~30-60 seconds per document
- **Total for 50 documents**: ~2-4 hours

The new RKB system includes:
- Better error recovery
- Progress tracking
- Resumable processing
- Document deduplication

## Troubleshooting

### Common Issues

**1. "Extractor failed" errors**
```bash
# Check individual PDF extraction
rkb extract problematic_file.pdf --verbose

# Skip problematic files and continue with others
```

**2. "Vector database not found"**
```bash
# Ensure indexing completed successfully
rkb index --project-id PROJECT_ID
```

**3. "No results found" in search**
```bash
# Verify documents were indexed
rkb search --stats

# Check project documents
rkb project show PROJECT_ID
```

### Performance Optimization

**For Large Document Sets**:
```bash
# Process in smaller batches
rkb pipeline --data-dir "/path/to/pdfs" --num-files 20

# Use force-reprocess sparingly
rkb pipeline --force-reprocess  # Only when needed
```

**Memory Issues**:
- Process fewer files at once (`--num-files 10`)
- Restart Ollama service if embeddings fail
- Monitor system memory usage

## Data Cleanup (Optional)

After successful migration, you can clean up old nugget data:

```bash
# Remove old vector database (after confirming new system works)
rm -rf nugget/chroma_db/

# Remove old extraction files (after confirming new extractions work)
rm -rf nugget/extracted/

# Keep nugget/ directory for reference until fully satisfied
```

## Advanced Features

### Experiment Tracking
Create experiments to compare different processing configurations:

```bash
# Create experiment configurations
rkb experiment create "Chroma Embedding" --embedder chroma
rkb experiment create "Ollama Embedding" --embedder ollama

# Compare results
rkb experiment compare exp_12345 exp_67890 --queries "machine learning" "neural networks"
```

### Document Subsets
Create targeted document collections:

```bash
# Create subset of recent papers
rkb project subset "Recent Papers" \
  --date-from 2024-01-01 \
  --status indexed \
  --limit 20
```

## Validation Checklist

- [ ] All original PDFs processed successfully
- [ ] Search returns relevant results for familiar queries
- [ ] Document count matches expectations
- [ ] Interactive search mode works
- [ ] Project statistics show expected numbers
- [ ] Vector database contains embeddings

## Getting Help

If you encounter issues during migration:

1. **Check verbose output**: Add `--verbose` to any command
2. **Review logs**: Check console output for specific error messages
3. **Test individual components**: Try extract/index steps separately
4. **Verify prerequisites**: Ensure Ollama is running and accessible

## Next Steps

After successful migration:

1. **Set up regular workflows** using RKB commands
2. **Explore experiment features** for research optimization
3. **Create project-specific collections** for different research areas
4. **Set up automation scripts** using the RKB CLI

The new RKB system provides enhanced capabilities for research document management while maintaining compatibility with your existing workflows.