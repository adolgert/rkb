# System-Level Integration Tests

## Overview

This directory contains system-level integration tests for RKB CLI commands. These tests validate end-to-end workflows using temporary storage for complete isolation.

## Test Structure

- **test_cli_integration.py** - Phase 1: Basic CLI workflows (pipeline→search, pipeline→documents, extract→index)
- **test_cli_extended.py** - Phase 2: Extended workflows (projects, find, stats, dry-run)
- **test_cli_errors.py** - Phase 3: Error handling and edge cases
- **test_cli_real_data.py** - Phase 4: Real data end-to-end tests with actual PDF processing
- **test_cli_state.py** - Phase 5: State consistency across command invocations

## Current Status

### ✅ Working Tests
- Error case tests (missing directories, no documents, etc.)
- Tests that don't require PDF extraction

### ⚠️  Tests Requiring Nougat
Most workflow tests require working Nougat extraction and are currently **failing** because:

1. **Root cause identified**: `transformers==4.56.2` is installed but nougat requires `transformers==4.38.2`
2. **Error**: `TypeError: BARTDecoder.prepare_inputs_for_inference() got an unexpected keyword argument 'cache_position'`
3. **Impact**: All tests that call nougat extraction fail (10+ tests)
4. **Test data exists**: PDFs are successfully copied from `data/initial/` (65 PDFs available)

### Test Failures (from zerror.txt)

**Common pattern**: All tests calling `pipeline_cmd` fail with:
```
WARNING  rkb.extractors.nougat_extractor:nougat_extractor.py:249     Chunk 1-1: Unknown error (pages 1-1)
...
WARNING  rkb.pipelines.ingestion_pipeline:ingestion_pipeline.py:147   Extraction failed: No content extracted from any chunks
```

**Result**: Pipeline completes but processes 0 documents successfully.

## Running Tests

### Run all tests (most will skip if nougat not working):
```bash
pytest tests/system/ -v
```

### Run only error tests (these should pass):
```bash
pytest tests/system/test_cli_errors.py -v
```

### Skip slow tests:
```bash
pytest tests/system/ -v -m "not slow"
```

## Prerequisites for Full Test Suite

For all tests to pass, you need:

1. **Working Nougat installation**:
   - Correct albumentations version (1.2.1)
   - Correct transformers version (≤4.38.2)
   - GPU available (or CPU-only nougat configured)
   - Nougat models downloaded

2. **Test data**:
   - PDF files in `data/initial/`
   - PDFs must be processable by nougat

3. **Environment**:
   - Dependencies from `pyproject.toml[nougat]` installed
   - Sufficient memory for PDF processing

## Test Design

All tests use:
- **pytest's `tmp_path` fixture** for temporary directories
- **Complete isolation** - all databases and extractions in temp dirs
- **Proper cleanup** - pytest automatically removes temp directories
- **Test parameters match CLI** - tests call actual CLI execute() functions

## Fixing Nougat Issues

**Fix the transformers version conflict:**

```bash
pip install 'transformers==4.38.2' --force-reinstall
```

This will downgrade transformers from 4.56.2 to 4.38.2, which is compatible with nougat-ocr.

After fixing, verify nougat works:
```bash
nougat data/initial/2005.07062v1.pdf --out /tmp/test_extract --pages 1-1
```

**Why this happens:**
- `pyproject.toml` specifies `transformers==4.38.2`
- But pip installed `transformers==4.56.2` (likely from another dependency)
- Newer transformers added `cache_position` parameter that breaks nougat
- Our patch in `nougat_extractor.py` only works for Python API, not CLI commands

## Known Issues

1. **albumentations version conflict** - Fixed by downgrading to 1.2.1
2. **Nougat extraction failing** - Needs investigation
3. **`find_cmd` test** - Fixed parameter mismatch (output vs output_file)
