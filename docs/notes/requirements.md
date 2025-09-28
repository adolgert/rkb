# Research Knowledge Base - Requirements

## Overview

This document defines the functional and non-functional requirements for a personal research knowledge base system. The system processes a large collection of academic PDFs to enable semantic search, question-answering, and research assistance.

## 1. Semantic Search Requirements (Detailed)

### 1.1 Query Capabilities

**Basic Search**
- Text-based queries in natural language
- Mathematical concept queries (e.g., "hazard rate integrals")
- Author-based searches
- Topic/domain-based searches
- Boolean operators support (AND, OR, NOT)

**Advanced Search**
- Equation-aware search (LaTeX syntax in queries)
- Multi-modal queries (text + equation patterns)
- Temporal constraints (papers from specific years)
- Citation-based queries ("papers citing Smith 2020")
- Find papers that are in a particular Journal.
- Similarity search ("papers like this one")

**Query Examples**
```
- "Bayesian inference for time series"
- "survival analysis hazard function"
- "papers about MCMC convergence diagnostics"
- "\\lambda(t) = \\alpha \\beta t^{\\beta-1}" (LaTeX equation search)
- "neural networks AND optimization"
- "author:Smith AND year:>2020"
```

### 1.2 Result Presentation

**Granularity Levels**
- Chunk-level results (current prototype behavior)
- Document-level aggregation (paper recommendations)
- Section-level results (chapter/section identification). This could be approximated by looking at page-level results that are near each other within a larger document.
- Page-level results (specific page references)

**Result Information**
- Relevance score (similarity metric)
- Source document title and authors
- Publication year and venue
- Snippet/preview of matching content
- Page numbers in original PDF
- Equation indicators (✓/✗ for math content)
- Link to original PDF file

**Ranking and Filtering**
- Sort by relevance, date, author, citation count
- Filter by equation presence/absence
- Filter by document type (journal, conference, preprint)
- Filter by date ranges
- Minimum relevance threshold
- Diversity optimization (avoid multiple results from same paper)

### 1.3 Performance Requirements

**Response Time**
- We expect response time on this small computer to be slow, and that's OK.
- Search queries: < 10 seconds for results
- Simple queries: < 500ms preferred
- Complex multi-filter queries: < 60 seconds acceptable
- Document-level aggregation: < 30 seconds

**Throughput**
- Support 10+ concurrent searches (personal use)
- Batch query processing for analysis tasks
- No degradation with corpus size up to 10,000 papers

**Accuracy**
- High precision for mathematical concept searches
- Minimal false positives for specific technical terms
- Consistent ranking across similar queries
- Recall: find relevant papers even with different terminology

### 1.4 Search Quality Metrics

**Measurable Goals**
- Precision@5 > 80% for domain-specific queries
- Mathematical concept recall > 70%
- Response time consistency (± 20% variance)
- Zero-result queries < 5% for reasonable queries

**Test Cases**
- "hazard rate function" should find survival analysis papers
- "MCMC convergence" should find Bayesian computation papers
- LaTeX equation searches should match mathematical content
- Author searches should be case-insensitive
- Typo tolerance for common technical terms

## 2. Data Handling Requirements

### 2.1 Document Lifecycle Management

**Ingestion**
- Support PDF files from multiple sources (ArXiv, journals, personal)
- Support LaTeX files from multiple sources (ArXiv, personal) (pandoc paper.tex -o paper.mmd --from latex --to markdown --wrap=none)
- Automatic duplicate detection via content hashing
- Metadata extraction from PDFs and filenames
- Error handling for corrupted or unsupported files
- Batch processing capabilities
- Progress tracking and logging
- Support for watching for additions of new files to input directories.

**Configuration**
- Settings to for input directories.
- Ability to handle files with the same name by putting them within unique directories (like Zotero does).
- Ability to specify locations for output and intermediate data in order to handle data sizes on different disks. 

**Storage**
- Immutable source documents (never modify originals)
- Multiple extraction formats per document
- Version history for updated papers
- Referential integrity between all derivatives
- Efficient storage (avoid duplicate extractions)

**Updates and Deletion**
- Cascade deletion (PDF → extraction → embeddings → search index)
- Archive old versions rather than destructive updates
- Support for manual document corrections
- Rollback capability for failed updates

### 2.2 Deduplication Strategy

**Content-Based Detection**
- SHA-256 hashing of PDF content
- Fuzzy matching for near-duplicates (different resolutions)
- DOI-based matching when available
- File size and page count heuristics

**Resolution Strategy**
- Prefer higher resolution versions
- Prefer published over preprint versions
- Manual review interface for ambiguous cases
- Configurable policies for different duplicate types

### 2.3 Version Control

**Document Provenance**
- Track all processing steps and timestamps
- Record extraction tool versions and parameters
- Maintain audit log of all changes
- Support reproducible processing
- Quality metrics at each processing stage

### 2.4 Metadata Management

**Required Metadata**
- Document hash (content identification)
- File path and size
- Title and authors (extracted or manual)
- Publication date and venue
- ArXiv ID, DOI when available
- Processing timestamps and tool versions

**Optional Metadata**
- Abstract text
- Keywords and subject classifications
- Citation count and impact metrics
- Related papers and citations
- Personal tags and notes
- Quality assessment scores

**Metadata Sources**
- PDF metadata fields
- Filename parsing (ArXiv IDs, DOI patterns)
- Content extraction (title, authors from first page)
- External APIs (ArXiv, CrossRef, Semantic Scholar)
- Manual entry interface
- Mendeley integration using exported Bibtex file.

### 2.5 Error Recovery and Data Integrity

**Processing Failures**
- Graceful handling of extraction failures
- Partial processing results preservation
- Retry mechanisms with exponential backoff
- Error categorization and reporting
- Manual intervention workflows

**Data Validation**
- Consistency checks across storage layers
- Orphaned data detection and cleanup
- Corruption detection and alerts
- Regular health checks and reporting
- Backup and restore capabilities

## 3. Question-Answering System Requirements (High-Level)

### 3.1 Query Processing
- Natural language question understanding
- Context-aware follow-up questions
- Multi-document synthesis capabilities
- Citation generation for answers

### 3.2 Answer Generation
- LLM integration (Claude, Gemini APIs)
- Source document evidence
- Confidence scoring
- Uncertainty acknowledgment

### 3.3 Interaction Modes
- Interactive chat interface
- Batch Q&A processing
- Export functionality for research workflows

## 4. Paper Recommendation System Requirements (High-Level)

### 4.1 Recommendation Types
- Topic-based recommendations
- Citation-based suggestions
- Author similarity recommendations
- Methodology-based suggestions
- Reading list generation

### 4.2 Context Awareness
- Current research project context
- Previously read paper tracking
- Interest area profiling
- Novelty vs. foundational balance

### 4.3 Presentation
- Ranked recommendation lists
- Justification for recommendations
- Related paper clustering
- Reading time estimates

## 5. Export and Integration Requirements (High-Level)

### 5.1 Data Export
- Search results to various formats (JSON, CSV, BibTeX)
- Full document sets for LLM analysis
- Metadata export for external tools
- Custom report generation

### 5.2 External Tool Integration
- Claude/Gemini file upload automation
- Citation manager integration (Zotero, Mendeley)
- Note-taking app connections
- Research database APIs

### 5.3 Workflow Automation
- Batch paper processing for AI analysis
- Automated bibliography generation
- Research project organization
- Cross-reference validation

## 6. Non-Functional Requirements

### 6.1 Performance Constraints

**Hardware Utilization**
- Efficient use of RTX 4060 GPU for embeddings
- Memory usage < 32GB for normal operations
- Storage growth: ~1GB per 1000 papers estimated
- CPU utilization balance for concurrent operations

**Scalability Targets**
- Support up to 10,000 documents initially
- Linear scaling to 50,000+ documents
- Graceful degradation under resource constraints
- Horizontal scaling potential for future growth

### 6.2 Reliability Requirements

**Uptime and Availability**
- Recovery time < 30 minutes for system failures
- Recovery from original PDFs expected to be less than 1 week.
- Uptime requirements are minimal.

**Data Durability**
- No data loss of original PDFs. Keep these safe.
- Regular integrity validation

### 6.3 Usability Requirements

**Interface Design**
- Command-line interface for power users
- Web interface for general searching
- API endpoints for programmatic access
- Batch operation support

**Learning Curve**
- Basic search: usable within 5 minutes
- Advanced features: learnable within 1 hour
- Administration tasks: documented procedures
- Error messages: actionable and clear

### 6.4 Extensibility Requirements

**Plugin Architecture**
- New extractor implementations
- Alternative embedding models
- Custom search algorithms
- External data source connectors

**Configuration Management**
- Experiment isolation and comparison
- A/B testing capabilities
- Feature flags for experimental features
- Environment-specific configurations

**API Design**
- RESTful service interfaces
- Versioned API endpoints
- Comprehensive API documentation
- MCP development potential.

## 7. Security and Privacy Requirements

### 7.1 Data Protection
- Personal research data remains local
- No unauthorized external transmission
- Secure API key management
- Access logging and audit trails

### 7.2 System Security
- Input validation for all user queries
- Safe PDF processing (sandbox extraction)
- Regular security updates for dependencies
- Minimal external service dependencies

## 8. Compliance and Ethics Requirements

### 8.1 Copyright Compliance
- Personal use only (no redistribution)
- Respect fair use guidelines
- No bulk downloading from restricted sources
- Clear attribution in generated citations

### 8.2 Responsible AI Use
- Transparent AI assistance labeling
- Bias awareness in search results
- Fact-checking reminders for AI-generated content
- User agency in AI-assisted workflows

---

## Requirements Status

**Completed Analysis:**
- Semantic search detailed requirements ✓
- Data handling comprehensive requirements ✓
- Current prototype evaluation ✓

**Pending Definition:**
- Q&A system detailed requirements
- Recommendation system specifications
- Integration workflow details
- Performance benchmark definitions

**Future Considerations:**
- Multi-user support (if sharing with colleagues)
- Cloud deployment options
- Mobile access requirements
- Collaborative features

---

*Last Updated: 2025-09-28*
*Document Version: 1.0*