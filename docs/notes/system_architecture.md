Proposed System Architecture: Research Knowledge Base (RKB)

  What Could be Built on Top of This

   - We could make a browser-based search engine.
   - We could make an MCP server for agents to use to understand our particular domain.
   - We could make an agent that looks at most recent file additions and looks up previous work.
   - We could look at the corpus of writing and code that we have on disk and cross-reference it with publications.
   - We could make a speech-to-text interface to perform queries and a text-to-speech interface to describe chunks.

  Core Design Principles

  - **Experimental Flexibility**: Primary goal - easy experimentation with document subsets, embeddings, and search methods
  - **Separation of Concerns**: Each layer has a single responsibility
  - **Project-Based Organization**: Documents can be logically grouped into research projects for focused experimentation (projects are filters, not data silos)
  - **Data Immutability**: Source documents never modified, all derivatives tracked
  - **Rebuild Capability**: System can be completely reconstructed from original PDFs
  - **Reproducibility**: All transformations are deterministic and logged

  Architecture Layers

  ┌─────────────────────────────────────────────────────────────┐
  │                    Application Layer                         │
  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
  │  │  Search  │  │    Q&A   │  │  Paper   │  │  Export  │  │
  │  │    UI    │  │   Agent  │  │  Recomm  │  │  Claude  │  │
  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
  └─────────────────────────────────────────────────────────────┘
                                │
                                ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                     Service Layer                            │
  │  ┌──────────────────────────────────────────────────────┐  │
  │  │            Unified Query Interface (API)              │  │
  │  └──────────────────────────────────────────────────────┘  │
  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────┐  │
  │  │ Project │  │Experiment│  │ Semantic│  │   Version   │  │
  │  │ Manager │  │Comparer │  │  Search │  │   Control   │  │
  │  └─────────┘  └─────────┘  └─────────┘  └─────────────┘  │
  └─────────────────────────────────────────────────────────────┘
                                │
                                ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                   Processing Layer                           │
  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
  │  │   Extractor  │  │   Embedder   │  │    Enrichment    │  │
  │  │   Registry   │  │   Registry   │  │     Registry     │  │
  │  └──────────────┘  └──────────────┘  └──────────────────┘  │
  │  ┌─────┐ ┌─────┐  ┌──────┐┌──────┐  ┌──────┐ ┌────────┐  │
  │  │Nugat│ │PyMu │  │Ollama││OpenAI│  │ArXiv │ │Mendeley│  │
  │  └─────┘ └─────┘  └──────┘└──────┘  └──────┘ └────────┘  │
  └─────────────────────────────────────────────────────────────┘
                                │
                                ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                     Storage Layer                            │
  │  ┌──────────────────────────────────────────────────────┐  │
  │  │              Document Registry (SQLite)               │  │
  │  │  - doc_id, content_hash, arxiv_id, version           │  │
  │  │  - project_memberships, experiment_embeddings        │  │
  │  └──────────────────────────────────────────────────────┘  │
  │  ┌─────────┐  ┌─────────┐  ┌─────────────────────────┐  │
  │  │  Source │  │Extracted│  │     Shared Vector       │  │
  │  │   PDFs  │  │   Text  │  │     Database (Chroma)   │  │
  │  │         │  │         │  │   (project_id filtering)│  │
  │  └─────────┘  └─────────┘  └─────────────────────────┘  │
  └─────────────────────────────────────────────────────────────┘

  Package Component Specifications

  1. Document Registry (Core Layer - rkb.core.document_registry)

  # document_registry.py
  class DocumentRegistry:
      """
      Single source of truth for all documents in the system.
      Tracks lineage from source PDF through all derivatives.
      Enables project-based organization and experiment tracking.
      """

      def register_document(pdf_path) -> doc_id:
          # Hash content, check duplicates, assign UUID

      def get_document_state(doc_id) -> DocumentState:
          # Return current processing status

      def create_project(project_name, description) -> project_id:
          # Create new research project container

      def add_documents_to_project(doc_ids, project_id):
          # Assign documents to research projects

      def get_project_documents(project_id) -> List[doc_id]:
          # Get all documents in a project

      def cascade_delete(doc_id):
          # Remove document and all derivatives

  Schema:
  CREATE TABLE documents (
      doc_id TEXT PRIMARY KEY,
      content_hash TEXT UNIQUE,
      arxiv_id TEXT,
      doi TEXT,
      title TEXT,
      authors JSON,
      source_path TEXT,
      added_date TIMESTAMP,
      updated_date TIMESTAMP,
      version INTEGER,
      parent_doc_id TEXT  -- For version tracking
  );

  CREATE TABLE document_projects (
      project_id TEXT PRIMARY KEY,
      project_name TEXT,
      description TEXT,
      created_date TIMESTAMP
  );

  CREATE TABLE document_project_membership (
      doc_id TEXT REFERENCES documents(doc_id),
      project_id TEXT REFERENCES document_projects(project_id),
      added_date TIMESTAMP,
      PRIMARY KEY (doc_id, project_id)
  );

  CREATE TABLE extractions (
      extraction_id TEXT PRIMARY KEY,
      doc_id TEXT REFERENCES documents(doc_id),
      extractor_name TEXT,  -- 'nougat', 'pymupdf', 'pandoc'
      extractor_version TEXT,
      extraction_path TEXT,
      extraction_date TIMESTAMP,
      quality_score REAL,
      page_count INTEGER,
      status TEXT  -- 'complete', 'partial', 'failed'
  );

  CREATE TABLE experiment_embeddings (
      experiment_id TEXT PRIMARY KEY,
      project_id TEXT REFERENCES document_projects(project_id),  -- NULL for global
      experiment_name TEXT,
      embedder_name TEXT,  -- 'ollama-mxbai', 'openai-ada', etc
      embedder_config JSON,  -- Parameters, chunk size, etc
      vector_db_path TEXT,
      chunk_count INTEGER,
      created_date TIMESTAMP
  );

  2. Extractor Registry (Pluggable Extraction)

  # rkb/core/interfaces.py
  from abc import ABC, abstractmethod
  from pathlib import Path
  from rkb.core.models import ExtractionResult, EmbeddingResult

  class ExtractorInterface(ABC):
      @abstractmethod
      def extract(self, source_path: Path) -> ExtractionResult:
          """Extract text content from document."""

      @abstractmethod
      def get_capabilities(self) -> dict:
          """Return extractor capabilities (math, tables, speed, etc)."""

  class EmbedderInterface(ABC):
      @abstractmethod
      def embed(self, text_chunks: list[str]) -> EmbeddingResult:
          """Generate embeddings for text chunks."""

  # rkb/extractors/nougat_extractor.py
  from rkb.core.interfaces import ExtractorInterface
  from rkb.core.models import ExtractionResult

  class NougatExtractor(ExtractorInterface):
      def extract(self, source_path: Path) -> ExtractionResult:
          # Nougat-specific implementation with equation support

      def get_capabilities(self) -> dict:
          return {"handles_math": True, "handles_tables": True, "speed": "slow"}

  # rkb/extractors/pymupdf_extractor.py
  from rkb.core.interfaces import ExtractorInterface

  class PyMuPDFExtractor(ExtractorInterface):
      def extract(self, source_path: Path) -> ExtractionResult:
          # Fast text-only extraction

      def get_capabilities(self) -> dict:
          return {"handles_math": False, "handles_tables": True, "speed": "fast"}

  3. Project and Experiment Management

  # projects/hazard_models/experiments.yaml
  project_id: hazard_models
  project_name: "Survival Analysis and Hazard Models"
  experiments:
    baseline:
      experiment_id: "hazard_baseline"
      extractor: "nougat"
      embedder: "ollama-mxbai"
      chunk_size: 2000
      search_strategy: "semantic_only"
      vector_db_path: "rkb_chroma_db"  # Shared database with project filtering
      created_date: "2025-09-28T10:00:00Z"

    openai_comparison:
      experiment_id: "hazard_openai"
      extractor: "nougat"  # Reuse same extraction
      embedder: "openai-ada-002"
      chunk_size: 2000
      search_strategy: "semantic_only"
      vector_db_path: "rkb_chroma_db"  # Shared database with project filtering
      created_date: "2025-09-28T11:00:00Z"

    hybrid_approach:
      experiment_id: "hazard_hybrid"
      extractor: "nougat"
      embedder: "ollama-mxbai"
      chunk_size: 1000
      search_strategy: "hybrid_bm25_semantic"
      vector_db_path: "rkb_chroma_db"  # Shared database with project filtering
      created_date: "2025-09-28T12:00:00Z"

  # rkb/services/experiment_service.py
  from rkb.core.document_registry import DocumentRegistry
  from rkb.core.models import ExperimentConfig, ComparisonResult

  class ExperimentService:
      def __init__(self):
          self.registry = DocumentRegistry()

      def create_project_experiment(self, project_id: str, experiment_config: ExperimentConfig) -> str:
          """Create isolated experiment on project subset."""

      def compare_experiments(self, experiment_ids: list[str], test_queries: list[str]) -> ComparisonResult:
          """Side-by-side comparison of experiments."""

      def switch_active_experiment(self, experiment_id: str) -> None:
          """Change active search experiment."""

  4. Service APIs

  # rkb/services/search_service.py
  from rkb.core.document_registry import DocumentRegistry
  from rkb.core.models import SearchResult, DocumentResult, ComparisonResult

  class SearchService:
      def __init__(self, experiment_id: str | None = None, project_id: str | None = None):
          self.registry = DocumentRegistry()
          self.experiment_config = self._load_experiment_config(experiment_id)
          self.project_docs = self.registry.get_project_documents(project_id) if project_id else None
          self.vector_db = self._connect_vector_db("rkb_chroma_db")  # Shared database

      def search(self, query: str, filters: dict | None = None) -> list[SearchResult]:
          """Experiment-specific search with optional project filtering."""

      def search_by_document(self, query: str) -> list[DocumentResult]:
          """Aggregate chunks to document level."""

      def compare_search(self, query: str, experiment_ids: list[str]) -> ComparisonResult:
          """Run same query across multiple experiments."""

  # rkb/services/project_service.py
  from rkb.core.document_registry import DocumentRegistry
  from rkb.core.models import ProjectStats

  class ProjectService:
      def __init__(self):
          self.registry = DocumentRegistry()

      def create_project_from_search(self, query: str, project_name: str) -> str:
          """Create project by selecting documents matching query."""

      def add_documents_by_filter(self, project_id: str, filters: dict) -> int:
          """Add documents to project based on metadata filters."""

      def get_project_statistics(self, project_id: str) -> ProjectStats:
          """Document count, extraction status, available experiments."""

  5. Pipeline Orchestration

  # rkb/pipelines/ingestion_pipeline.py
  from pathlib import Path
  from rkb.core.document_registry import DocumentRegistry
  from rkb.extractors import get_extractor
  from rkb.embedders import get_embedder
  from rkb.core.models import ExperimentConfig

  class IngestionPipeline:
      def __init__(self, experiment_config: ExperimentConfig):
          self.registry = DocumentRegistry()
          self.extractor = get_extractor(experiment_config.extractor)
          self.embedder = get_embedder(experiment_config.embedder)
          self.config = experiment_config

      def process_document(self, source_path: Path) -> str:
          """Process document through full ingestion pipeline."""
          # 1. Register in document registry
          doc_id = self.registry.register_document(source_path)

          # 2. Extract text (experiment-specific)
          extraction = self.extractor.extract(source_path)
          extraction_id = self.registry.add_extraction(doc_id, extraction)

          # 3. Generate embeddings (experiment-specific)
          embeddings = self.embedder.embed(extraction.chunks)
          embedding_id = self.registry.add_embeddings(extraction_id, embeddings)

          # 4. Index in vector database
          self._index_embeddings(embeddings, doc_id)

          return doc_id

      def _index_embeddings(self, embeddings, doc_id: str) -> None:
          """Index embeddings in vector database."""

  Python Package Structure

  kbase/                         # Project root
  ├── pyproject.toml            # Package configuration with import-linter rules
  ├── README.md                 # Project documentation
  ├── rkb/                      # Main Python package
  │   ├── __init__.py           # Package exports and version
  │   ├── core/                 # Core layer (bottom of hierarchy)
  │   │   ├── __init__.py
  │   │   ├── document_registry.py   # Central document tracking
  │   │   ├── interfaces.py          # Abstract base classes
  │   │   └── models.py             # Data models
  │   │
  │   ├── extractors/           # Processing layer
  │   │   ├── __init__.py       # Extractor registry
  │   │   ├── base.py           # Base extractor functionality
  │   │   ├── nougat_extractor.py    # Nougat OCR implementation
  │   │   ├── pymupdf_extractor.py   # PyMuPDF implementation
  │   │   └── pandoc_extractor.py    # LaTeX/Pandoc conversion
  │   │
  │   ├── embedders/            # Processing layer (parallel to extractors)
  │   │   ├── __init__.py       # Embedder registry
  │   │   ├── base.py           # Base embedder functionality
  │   │   ├── ollama_embedder.py     # Local Ollama integration
  │   │   └── openai_embedder.py     # OpenAI API integration
  │   │
  │   ├── pipelines/            # Pipeline orchestration layer
  │   │   ├── __init__.py
  │   │   ├── ingestion_pipeline.py  # Document processing workflows
  │   │   └── update_pipeline.py     # Version update workflows
  │   │
  │   ├── services/             # Service layer
  │   │   ├── __init__.py
  │   │   ├── search_service.py      # Semantic search
  │   │   ├── project_service.py     # Project management
  │   │   └── experiment_service.py  # Experiment comparison
  │   │
  │   └── cli/                  # CLI layer (top of hierarchy)
  │       ├── __init__.py
  │       ├── main.py           # Main CLI entry point
  │       ├── search.py         # Search commands
  │       ├── project.py        # Project commands
  │       └── experiment.py     # Experiment commands
  │
  ├── tests/                    # Test suite
  │   ├── __init__.py
  │   ├── unit/                 # Unit tests for individual components
  │   │   ├── __init__.py
  │   │   ├── test_core/
  │   │   ├── test_extractors/
  │   │   ├── test_embedders/
  │   │   ├── test_services/
  │   │   └── test_pipelines/
  │   ├── integration/          # Integration tests for component interactions
  │   │   ├── __init__.py
  │   │   └── test_workflows/
  │   └── e2e/                  # End-to-end workflow tests
  │       ├── __init__.py
  │       └── test_complete_pipeline/
  │
  ├── docs/                     # Documentation
  │   ├── notes/
  │   │   └── system_architecture.md
  │   └── api/                  # Auto-generated API docs
  │
  ├── projects/                 # Research project data (not in package)
  │   ├── hazard_models/
  │   │   ├── documents.json          # Project document subset
  │   │   ├── experiments.yaml        # Project-specific experiments
  │   │   └── results/               # Experiment comparison results
  │   ├── mcmc_diagnostics/
  │   └── time_series_analysis/
  │
  ├── storage/                  # System data (not in package)
  │   ├── documents.db          # SQLite registry with projects
  │   ├── source_pdfs/          # Immutable original PDFs/LaTeX
  │   ├── extractions/          # Shared extracted text (MMD)
  │   └── rkb_chroma_db/        # Shared vector database for all projects
  │
  └── legacy/                   # Migration from prototype
      └── nugget/               # Original prototype code

  Key Benefits

  1. **Experimental Flexibility** (Primary Goal)
    - Select document subsets for focused research projects
    - Try multiple embeddings/search methods on same document sets
    - Easy experiment switching and comparison
    - Isolated experimentation without breaking existing work

  2. **Rebuild Capability**
    - Complete system reconstruction from original PDFs
    - All processing steps documented and reproducible
    - Data integrity checks and validation
    - Recovery from failures in < 1 week

  3. **Project Organization**
    - Group documents by research area or topic
    - Project-specific experiments and configurations
    - Easy management of related document collections
    - Support for multiple concurrent research projects

  4. **Practical Features**
    - Support for PDF and LaTeX input files
    - Directory watching for new file detection
    - Multiple storage locations for large datasets
    - Content-based deduplication

  5. **Package Architecture Benefits**
    - **Import enforcement**: import-linter prevents layer violations
    - **Clean APIs**: Proper module boundaries and public interfaces
    - **Testing support**: Full pytest integration with coverage
    - **Development tools**: Ruff formatting, mypy type checking
    - **Installable**: `pip install -e .` for development
    - **CLI integration**: Single entry point with subcommands
    - **Documentation**: Sphinx-ready structure

  6. **Extensibility**
    - Add new extractors through ExtractorInterface
    - Plugin architecture for embedding models via EmbedderInterface
    - MCP server development potential in services layer
    - Clean API boundaries for external integrations

  ## Import-Linter Layer Enforcement

  The package structure enforces a strict layered architecture:

  ```
  CLI Layer (rkb.cli)              # Top layer
      ↓ can import from
  Services Layer (rkb.services)    # Business logic
      ↓ can import from
  Pipelines Layer (rkb.pipelines)  # Orchestration
      ↓ can import from
  Processing Layer (rkb.extractors | rkb.embedders)  # Same level
      ↓ can import from
  Core Layer (rkb.core)            # Foundation - cannot import from above
  ```

  **Key Rules:**
  - Core layer is completely isolated (no upward imports)
  - Processing layers cannot import from services or CLI
  - Extractors and embedders can import from each other
  - Services cannot import from CLI
  - Ruff TID rule prevents local imports that bypass layer system

  This architecture prioritizes your experimental workflow while maintaining the robustness and clean boundaries needed for a scalable personal research system.
