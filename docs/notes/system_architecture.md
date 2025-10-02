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
  - **Project Isolation**: Each project is a self-contained directory with its own extraction database and experiments
  - **Extractor Version Stability**: Projects are tied to specific extractor versions; upgrading = new project
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
  │  │         Project Root (projects/)                      │  │
  │  │  ├── nougat_v1/                                      │  │
  │  │  │   ├── extractions.db (docs + extractions)        │  │
  │  │  │   └── experiments/                                │  │
  │  │  │       ├── baseline/                               │  │
  │  │  │       │   ├── experiment.db (chunks metadata)    │  │
  │  │  │       │   └── chroma_db/ (vectors)               │  │
  │  │  │       └── large_chunks/                           │  │
  │  │  │           ├── experiment.db                       │  │
  │  │  │           └── chroma_db/                          │  │
  │  │  └── nougat_v2/                                      │  │
  │  │      ├── extractions.db                              │  │
  │  │      └── experiments/                                │  │
  │  │          └── baseline/                               │  │
  │  │              ├── experiment.db                       │  │
  │  │              └── chroma_db/                          │  │
  │  └──────────────────────────────────────────────────────┘  │
  │  ┌─────────────────────────────────────────────────────┐  │
  │  │  Source PDFs (data/initial/)                        │  │
  │  │  - Immutable original files                         │  │
  │  │  - Read-only, never modified                        │  │
  │  └─────────────────────────────────────────────────────┘  │
  └─────────────────────────────────────────────────────────────┘

  Package Component Specifications

  1. Project Registry (Core Layer - rkb.core.project_registry)

  # project_registry.py
  class ProjectRegistry:
      """
      Manages multiple independent projects.
      Each project is a self-contained directory with its own database.
      """

      def create_project(name: str, extractor_config: dict) -> Project:
          # Create new project directory with extractions.db

      def list_projects() -> list[str]:
          # List all project directories

      def get_project(name: str) -> Project:
          # Load existing project

      def delete_project(name: str):
          # Remove entire project directory and all experiments

  # project.py
  class Project:
      """
      Self-contained project with extractions and experiments.
      Tied to specific extractor version.
      """

      def __init__(self, project_dir: Path):
          self.project_dir = project_dir
          self.extraction_registry = DocumentRegistry(
              project_dir / "extractions.db"
          )

      def extract_documents(pdf_paths: list[Path]) -> dict:
          # Extract all documents into this project

      def create_experiment(name: str, params: dict) -> Experiment:
          # Create experiment within this project

      def list_experiments() -> list[str]:
          # List experiments in this project

      def delete_experiment(name: str):
          # Delete experiment (extractions untouched)

  Project-Level Schema (extractions.db per project):
  CREATE TABLE documents (
      doc_id TEXT PRIMARY KEY,
      content_hash TEXT,
      source_path TEXT,
      arxiv_id TEXT,
      doi TEXT,
      title TEXT,
      authors TEXT,  -- JSON array
      added_date TIMESTAMP
  );

  CREATE TABLE extractions (
      extraction_id TEXT PRIMARY KEY,
      doc_id TEXT REFERENCES documents(doc_id),
      extractor_name TEXT,
      extractor_version TEXT,  -- Fixed for this project
      content TEXT,  -- Extracted markdown
      page_count INTEGER,
      extraction_date TIMESTAMP,
      status TEXT  -- 'complete', 'partial', 'failed'
  );

  CREATE TABLE project_config (
      key TEXT PRIMARY KEY,
      value TEXT  -- JSON
  );

  Experiment-Level Schema (experiment.db per experiment):
  CREATE TABLE chunks (
      chunk_id TEXT PRIMARY KEY,
      extraction_id TEXT,  -- References extraction in parent project
      doc_id TEXT,         -- For convenience
      content TEXT,
      page_numbers TEXT,   -- JSON array [3, 4, 5]
      chunk_index INTEGER,
      chunk_length INTEGER,
      has_equations INTEGER,
      display_eq_count INTEGER,
      inline_eq_count INTEGER,
      created_date TIMESTAMP
  );

  CREATE TABLE experiment_config (
      key TEXT PRIMARY KEY,
      value TEXT  -- JSON: chunking params, embedding model, etc
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

  3. Experiment Management

  # experiment.py
  class Experiment:
      """
      Experiment with specific chunking/embedding parameters.
      Lives within a project directory.
      """

      def __init__(self, name: str, exp_dir: Path, extraction_registry: DocumentRegistry, params: dict):
          self.name = name
          self.exp_dir = exp_dir
          self.extraction_registry = extraction_registry
          self.params = params
          self.db = sqlite3.connect(exp_dir / "experiment.db")
          self.embedder = ChromaEmbedder(db_path=exp_dir / "chroma_db")

      def build_from_extractions(self, force: bool = False):
          """Build this experiment from project extractions."""
          # Get all extractions from project
          # Chunk using experiment parameters
          # Store chunks in experiment.db
          # Embed chunks in chroma_db/

      def search(self, query: str, top_k: int = 10) -> list[ChunkResult]:
          """Search this experiment."""

      def get_statistics(self) -> dict:
          """Get experiment statistics."""

  # Example project config (projects/nougat_v1/config.yaml):
  project_name: "Nougat v1 Extraction"
  extractor:
    name: "nougat"
    version: "0.1.17"
  created_date: "2025-09-28T10:00:00Z"

  # Example experiment config (in experiment.db):
  {
      "chunk_size": 2000,
      "chunk_overlap": 0,
      "embedder_name": "ollama-mxbai",
      "embedder_model": "mxbai-embed-large",
      "search_strategy": "semantic_only"
  }

  # rkb/services/experiment_service.py
  from rkb.core.project_registry import ProjectRegistry
  from rkb.core.models import ComparisonResult

  class ExperimentService:
      def __init__(self):
          self.project_registry = ProjectRegistry()

      def create_experiment(self, project_name: str, exp_name: str, params: dict) -> Experiment:
          """Create experiment within project."""
          project = self.project_registry.get_project(project_name)
          return project.create_experiment(exp_name, params)

      def compare_experiments(
          self,
          project_name: str,
          exp_names: list[str],
          test_queries: list[str]
      ) -> ComparisonResult:
          """Side-by-side comparison of experiments within same project."""

      def delete_experiment(self, project_name: str, exp_name: str):
          """Delete experiment (project extractions untouched)."""

  4. Service APIs

  # rkb/services/search_service.py
  from rkb.core.project_registry import ProjectRegistry
  from rkb.core.models import SearchResult, DocumentResult

  class SearchService:
      def __init__(self, project_name: str, experiment_name: str):
          self.project_registry = ProjectRegistry()
          self.project = self.project_registry.get_project(project_name)
          self.experiment = self.project.get_experiment(experiment_name)

      def search(self, query: str, top_k: int = 10) -> list[SearchResult]:
          """Search within this experiment."""
          return self.experiment.search(query, top_k)

      def search_by_document(self, query: str) -> list[DocumentResult]:
          """Aggregate chunk results to document level."""

  # rkb/services/project_service.py
  from rkb.core.project_registry import ProjectRegistry
  from rkb.core.models import ProjectStats

  class ProjectService:
      def __init__(self):
          self.project_registry = ProjectRegistry()

      def create_project(self, name: str, extractor_config: dict) -> str:
          """Create new project directory."""
          return self.project_registry.create_project(name, extractor_config)

      def list_projects(self) -> list[str]:
          """List all projects."""
          return self.project_registry.list_projects()

      def get_project_statistics(self, project_name: str) -> ProjectStats:
          """Document count, extraction status, available experiments."""
          project = self.project_registry.get_project(project_name)
          return project.get_statistics()

      def delete_project(self, project_name: str):
          """Delete entire project directory."""
          self.project_registry.delete_project(project_name)

  5. Pipeline Orchestration

  # rkb/pipelines/extraction_pipeline.py
  from pathlib import Path
  from rkb.core.project_registry import Project
  from rkb.extractors import get_extractor

  class ExtractionPipeline:
      """Extracts documents into a project (project-level)."""

      def __init__(self, project: Project):
          self.project = project
          self.extractor = get_extractor(project.config["extractor_name"])

      def extract_documents(self, pdf_paths: list[Path], resume: bool = True) -> dict:
          """Extract all documents into project."""
          # With checkpoint/resume support
          for pdf_path in pdf_paths:
              # 1. Hash and check for duplicates
              # 2. Extract text
              # 3. Store in project's extractions.db
          return {"extracted": count, "skipped": skip_count}

  # rkb/pipelines/experiment_pipeline.py
  from rkb.core.project_registry import Project, Experiment
  from rkb.embedders import get_embedder

  class ExperimentPipeline:
      """Builds an experiment from project extractions (experiment-level)."""

      def __init__(self, experiment: Experiment):
          self.experiment = experiment
          self.embedder = get_embedder(experiment.params["embedder_name"])

      def build_experiment(self, force: bool = False) -> dict:
          """Build experiment from project extractions."""
          # 1. Get all extractions from project
          extractions = self.experiment.extraction_registry.get_all_extractions()

          # 2. Chunk using experiment parameters
          for extraction in extractions:
              chunks = self._chunk_text(
                  extraction.content,
                  self.experiment.params["chunk_size"]
              )
              # 3. Store chunks in experiment.db
              self.experiment.store_chunks(extraction.extraction_id, chunks)

          # 4. Embed all chunks
          all_chunks = self.experiment.get_all_chunks()
          embeddings = self.embedder.embed([c.content for c in all_chunks])

          # 5. Index in experiment's chroma_db/
          self._index_embeddings(embeddings, all_chunks)

          return {"chunks": len(all_chunks), "embeddings": len(embeddings)}

  Python Package Structure

  kbase/                         # Project root
  ├── pyproject.toml            # Package configuration with import-linter rules
  ├── README.md                 # Project documentation
  ├── rkb/                      # Main Python package
  │   ├── __init__.py           # Package exports and version
  │   ├── core/                 # Core layer (bottom of hierarchy)
  │   │   ├── __init__.py
  │   │   ├── project_registry.py    # Project management
  │   │   ├── document_registry.py   # Per-project document tracking
  │   │   ├── interfaces.py          # Abstract base classes
  │   │   └── models.py              # Data models
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
  │   │   ├── extraction_pipeline.py # Project-level extraction
  │   │   └── experiment_pipeline.py # Experiment-level chunking/embedding
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
  ├── projects/                 # Self-contained project directories (not in package)
  │   ├── nougat_v1/           # Project using Nougat v0.1.17
  │   │   ├── config.yaml              # Project config (extractor version, etc)
  │   │   ├── extractions.db           # Documents + extractions for this project
  │   │   └── experiments/            # Experiments within this project
  │   │       ├── baseline/
  │   │       │   ├── experiment.db   # Chunks metadata
  │   │       │   └── chroma_db/      # Vector database
  │   │       └── large_chunks/
  │   │           ├── experiment.db
  │   │           └── chroma_db/
  │   └── nougat_v2/           # New project with upgraded extractor
  │       ├── config.yaml
  │       ├── extractions.db
  │       └── experiments/
  │           └── baseline/
  │               ├── experiment.db
  │               └── chroma_db/
  │
  ├── data/                     # Source documents (not in package)
  │   └── initial/              # Immutable original PDFs/LaTeX
  │
  └── legacy/                   # Migration from prototype
      └── nugget/               # Original prototype code

  Key Benefits

  1. **Experimental Flexibility** (Primary Goal)
    - Projects are self-contained directories with specific extractor versions
    - Try multiple chunking/embedding methods within same project (experiments)
    - Easy experiment creation, deletion, and comparison
    - Isolated experimentation: deleting experiment doesn't affect project extractions

  2. **Extractor Upgrade Workflow**
    - Create new project directory for upgraded extractor
    - Old project remains searchable during week-long re-extraction
    - No complex versioning logic: projects are independent
    - Easy rollback: switch back to old project directory

  3. **Rebuild Capability**
    - Complete project reconstruction from original PDFs
    - All processing steps documented in project/experiment configs
    - Recovery: delete project, re-extract from source PDFs
    - Experiments rebuild quickly from cached project extractions

  4. **Simplified Operations**
    - Delete project: `rm -rf projects/project_name/`
    - Delete experiment: `rm -rf projects/project_name/experiments/exp_name/`
    - No cascade deletion logic needed (file system handles it)
    - No complex database schema migrations

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
