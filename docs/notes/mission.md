# Mission

## Background

I'm a researcher with a wide range of interests. I have a large body of papers, mostly as PDFs, that are a good representation of my past reading and work. Some I know very well, and many others I downloaded out of interest but haven't read. I want to use this body of literature to help me accomplish research goals.

## Goals

### High-level goals

 1. Use my reading time wisely.
 2. Improve my choices when I write papers.
 3. Improve my choices when I write code.

### Low-level goals

 1. Given the topic on my desk today, find related work both from my past papers and from the internet.
 2. Given a section of a paper I'm writing, show me related work.
 3. Given a question I have about a scientific topic, find relevant papers from my body of papers in order for me to either a) use them in my own AI-driven analysis or b) present them to an online research AI that accepts paper uploads.

### Example applications on this

   - We could make a browser-based search engine.
   - We could make an MCP server for agents to use to understand our particular domain.
   - We could make an agent that looks at most recent file additions and looks up previous work.
   - We could look at the corpus of writing and code that we have on disk and cross-reference it with publications.
   - We could make a speech-to-text interface to perform queries and a text-to-speech interface to describe chunks.

### Implementation goals

  1. PDF Content Extraction & Indexing
    - Extract text from your PDF collection
    - Create searchable embeddings database
    - Implement semantic search capabilities

  2. Research Assistant System
    - Topic-based paper recommendation
    - Related work finder for writing projects
    - Question-answering over your paper corpus

  3. Integration Workflows
    - Batch paper processing for Claude/Gemini upload
    - Citation management and reference formatting
    - Cross-referencing with online databases


## Available resources

 1. This computer has 64GB of memory, 4TB of disk, a Ryzen 5900x and an NVIDIA RTX 4060 GPU.
 2. I have paid subscriptions to Claude Pro and Google Gemini.
 3. Ollama is installed on this machine.
 4. There is a Mendeley installation that creates lists of the papers with metadata.
 5. I can find other resources if that helps.

### Potential bottlenecks:
  - PDF quality/OCR needs may vary significantly
  - Embedding model choice will affect search quality
  - Need to balance local vs cloud processing costs

### Recommended tech stack:

  - Ollama for local embeddings (sentence-transformers)

  - Vector database (Chroma/Qdrant)

  - Python ecosystem (PyPDF2, Langchain, etc.)
    * PyPDF2, pymupdf, Nougat
    * Langchain, DSPy.
    * docling

### Equation-Aware PDF Extraction

The plan is a hybrid approach:
  - Use pymupdf for text extraction
  - Detect equation regions (often in separate text blocks)
  - Process equations with Nougat or Mathpix
  - Combine results into searchable format

Resources
  1. Nougat (Meta) - Neural OCR model specifically designed for academic papers
    - Excellent at mathematical expressions and LaTeX conversion
    - Can run locally on your RTX 4060
    - Outputs markdown with proper LaTeX math notation
  2. Mathpix - Commercial OCR API specialized for math
    - High accuracy for equations and scientific notation
    - Has Python SDK for batch processing
    - Cost consideration for large collections
  3. pymupdf (fitz) + OCR pipeline
    - Better text extraction than PyPDF2
    - Can preserve layout and identify equation regions
    - Combine with specialized math OCR

## Requirements for PDF Content Extraction & Indexing

  Core Objectives

  - Extract text and mathematical equations from academic PDF corpus
  - Enable semantic search over extracted content
  - Research question: Determine utility of equation OCR for search and AI analysis

  Corpus Characteristics

  - Several thousand papers (~tens of thousands of pages)
  - File sizes: 1-300 pages (mostly ~15 pages)
  - Quality mix: mostly spotty text PDFs, some excellent (ArXiv), some scanned
  - Location: 1-2 subdirectories, managed via Mendeley
  - Duplicate detection needed (same papers at different resolutions/formats)

  Processing Requirements

  - Tool: Nougat-only for all extraction (no hybrid approach)
  - Sample size: 50 most recently downloaded papers for initial testing
  - Prioritization: Recent downloads first
  - Failure handling: Failed extractions should not halt pipeline
  - Processing mode: Batch processing acceptable
  - Duplicate detection: Separate cleanup step after initial OCR

  Mathematical Content

  - Focus: Inline math and display equations most important
  - Example use case: Search for hazard rate integrals (specific LaTeX forms)
  - Quality expectations: Unknown/experimental - will determine through testing

  Output Format

  - Storage: Structured markdown with embedded LaTeX equations
  - Structure: Page-based extraction (not section-aware)
  - Metadata: Maintain links to original PDF files and page numbers
  - Metadata priority: Content extraction is primary, metadata extraction is secondary

  Success Criteria

  - Ability to search mathematical concepts (e.g., hazard rate integrals)
  - Extraction pipeline processes corpus without manual intervention
  - Quality validation through manual spot-checking of sample papers

  Constraints

  - Personal use only (not building for others)
  - Local processing preferred (RTX 4060 GPU available)
  - Cost considerations for any external services

## Tool Dependencies Analysis

  Core Dependencies (Required)

  Nougat - PDF to markdown extraction
  - Risk: Unknown installation complexity, GPU compatibility
  - Alternative: None for equation-focused extraction
  - Code needed: Wrapper scripts, batch processing logic

  Ollama - Local embeddings generation
  - Risk: Low (already installed)
  - Models needed: sentence-transformers compatible model
  - Code needed: Embedding pipeline, text chunking

  Chroma - Vector database for search
  - Risk: Low (well-established)
  - Alternative: Qdrant, FAISS
  - Code needed: Schema design, indexing logic

  Standard Python Libraries

  pathlib, json, hashlib - File management, duplicate detection
  - Risk: Very low
  - Code needed: File discovery, metadata handling, deduplication

  Optional/Future Dependencies

  Langchain - RAG pipeline (for later Q&A feature)
  - Risk: Medium (complex framework)
  - When needed: Phase 2 (question-answering)
  - Alternative: Custom RAG implementation

  Claude/Gemini APIs - Advanced analysis (later phases)
  - Risk: Low (you have subscriptions)
  - When needed: Phase 2+

  Not Needed Initially

  DSPy - Complex LLM workflows (overkill for basic extraction)
  docling - Alternative extraction (redundant with Nougat)

  Unknown Dependencies

  Nougat's requirements - PyTorch, transformers, etc.
  Hardware compatibility - CUDA setup for RTX 4060

  Risk Assessment

  - Highest risk: Nougat installation/GPU setup
  - Medium risk: Batch processing performance at scale
  - Low risk: Everything else is well-established

  The core implementation is surprisingly lightweight - mostly glue code around Nougat + Ollama + Chroma.

## Implementation Choices

### Nougat Model Selection
- **Testing:** Use nougat-small (247M parameters, ~20s per 15 pages) for fast iteration and development
- **Production:** Use nougat-base (349M parameters, ~60s per 15 pages) for higher quality extraction
- **Rationale:** Small model sufficient for testing workflows; base model provides marginal quality improvement worth the extra time in production

### Page Limits
- **Testing:** 15 pages per PDF to fit within development timeouts and enable rapid testing
- **Production:** Remove page limits or increase significantly to capture full document content
- **Rationale:** Page limiting is a testing convenience, not a resource constraint
