# Implementation Plan: PDF Content Extraction & Indexing

## Phase 1: Environment Setup & Dependencies

### Local Service Configuration
- [x] Start Ollama service (`ollama serve`)
- [x] Verify GPU availability for Ollama (`nvidia-smi`)
- [x] Install/verify suitable embedding model in Ollama (e.g., `ollama pull mxbai-embed-large`)
- [x] Test Ollama embedding generation with sample text

### Python Environment Setup
- [ ] Create Python virtual environment for project
- [x] Install Nougat (`pip install nougat-ocr`)
- [ ] Install Chroma (`pip install chromadb`)
- [ ] Install supporting libraries (`pip install requests pathlib hashlib`)
- [x] Test Nougat installation with GPU support
- [x] Verify CUDA compatibility with RTX 4060

## Phase 2: Core Script Development

### File Discovery & Management
- [x] Create `find_recent.py` - identify 50 most recent PDFs from `data/initial`
- [x] Test file discovery script on current corpus
- [ ] Create `deduplicate.py` - detect duplicate PDFs by content hash
- [ ] Test duplicate detection on sample files

### PDF Processing Pipeline
- [x] Create `extract.py` - Nougat batch processing script
  - [x] Single PDF processing function
  - [x] Batch processing with error handling
  - [x] Progress tracking and logging
  - [x] Output structured markdown files
- [x] Test extraction on 3-5 sample PDFs with different quality levels
- [x] Validate markdown output format and LaTeX equation preservation
- [ ] STOP for human review of extraction at different quality levels.

### Vector Database & Search
- [x] Install Chroma
  - [x] Configure Chroma using PersistentClient API
  - [x] Test that Chroma is live with default embeddings
- [x] Create `index.py` - generate embeddings and populate Chroma
  - [x] Text chunking strategy (page-based, 2000 char chunks)
  - [x] Embedding generation via Chroma's default model
  - [x] Chroma database schema design with equation metadata
  - [x] Metadata linking (PDF file, chunk index, equation counts)
- [x] Create `search.py` - query interface
  - [x] Text similarity search with filtering options
  - [x] Mathematical concept search (tested with hazard rate example)
  - [x] Result ranking and display with equation indicators

## Phase 3: Integration & Testing

### End-to-End Pipeline
- [ ] Create `pipeline.py` - orchestrate full workflow
  - [ ] Find recent files → Extract → Index → Ready for search
  - [ ] Error handling and recovery
  - [ ] Progress reporting
- [ ] Process complete 50-paper sample set
- [ ] Validate extraction quality through manual spot-checking

### Search Validation
- [ ] Test mathematical concept search (hazard rate integrals)
- [ ] Test general topic search across different domains
- [ ] Verify page number and PDF file linking accuracy
- [ ] Performance testing (search speed, memory usage)

## Phase 4: Quality Assessment & Documentation

### Research Question Evaluation
- [ ] Manual review of equation extraction quality on 10 papers
- [ ] Test search effectiveness for mathematical concepts
- [ ] Document findings on equation OCR utility
- [ ] Performance metrics (processing time, accuracy estimates)

### Documentation & Next Steps
- [ ] Document script usage and configuration
- [ ] Identify successful patterns and failure modes
- [ ] Plan next implementation phase based on results
- [ ] Clean up temporary files and organize outputs

## Success Criteria

- [ ] All 50 sample papers processed without pipeline failures
- [ ] Successful semantic search for hazard rate integrals
- [ ] Clear assessment of equation OCR quality and utility
- [ ] Foundation ready for scaling to full corpus

## Fallback Plans

- [ ] If Nougat installation fails: Document issues and consider Mathpix API
- [ ] If GPU performance inadequate: Test CPU-only processing times
- [ ] If equation extraction poor: Validate text-only search quality
- [ ] If Ollama issues: Consider OpenAI embedding API as backup
