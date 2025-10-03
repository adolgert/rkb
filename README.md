# Research Knowledge Base (RKB)

A personal research knowledge base system for semantic search, document management, and experimental analysis of academic papers with equation-aware OCR capabilities.

## Features

- **Document Processing**: Extract text from PDFs and LaTeX files using Nougat OCR, PyMuPDF, and Pandoc
- **Semantic Search**: Vector-based search with support for mathematical equations and LaTeX notation
- **Project Organization**: Group documents into research projects for focused experimentation
- **Experimental Framework**: Try different embedding models and search strategies on document subsets
- **Version Control**: Track ArXiv paper versions and handle duplicates intelligently
- **Extensible Architecture**: Plugin system for extractors, embedders, and search strategies

## Installation

```bash
# Development installation
pip install -e ".[dev]"

# With optional dependencies
pip install -e ".[all]"  # All features
pip install -e ".[nougat,pdf]"  # OCR capabilities
```

### Requirements

- Python 3.12+ (tested with Python 3.13)
- For Nougat OCR: `albumentations==1.2.1` is required (pinned in dependencies)

### Known Issues

If you encounter MKL threading errors when using Nougat, the extractor automatically sets `MKL_SERVICE_FORCE_INTEL=1` to resolve conflicts between Intel MKL and libgomp.

## Quick Start

```bash
# Create a project and add documents
rkb project create survival_analysis "Papers on survival analysis methods"
rkb project add-documents survival_analysis --search "hazard rate function"

# Create embeddings for experimentation
rkb experiment create survival_analysis --embedder ollama-mxbai --name baseline
rkb experiment create survival_analysis --embedder openai-ada --name comparison

# Search and compare
rkb search --experiment baseline "lambda survival function"
rkb experiment compare baseline comparison --query "hazard rate integral"
```

## Architecture

The system follows a layered architecture with strict import controls:

- **CLI Layer**: Command line interface and user interactions
- **Services Layer**: High-level business logic and orchestration
- **Pipelines Layer**: Document processing workflows
- **Processing Layer**: Extractors and embedders (parallel layer)
- **Core Layer**: Base interfaces, models, and document registry

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Check code quality
ruff check .
ruff format .

# Verify architecture compliance
import-linter
```

## Project Structure

See `system_architecture.md` for detailed architectural documentation.