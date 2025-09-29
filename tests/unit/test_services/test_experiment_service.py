"""Tests for experiment service functionality."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from rkb.core.document_registry import DocumentRegistry
from rkb.core.models import ChunkResult, ExperimentConfig, SearchResult
from rkb.services.experiment_service import ExperimentService


class TestExperimentService:
    """Tests for ExperimentService."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        registry = DocumentRegistry(db_path)
        yield registry

        # Cleanup
        if db_path.exists():
            db_path.unlink()

    @pytest.fixture
    def mock_search_service(self):
        """Create mock search service."""
        search_service = Mock()
        # Mock search results
        chunk_results = [
            ChunkResult(
                chunk_id="chunk1",
                content="Test content about machine learning",
                similarity=0.85,
                distance=0.15,
                metadata={"doc_id": "doc1", "pdf_name": "test.pdf"},
            ),
            ChunkResult(
                chunk_id="chunk2",
                content="Another test content",
                similarity=0.75,
                distance=0.25,
                metadata={"doc_id": "doc2", "pdf_name": "test2.pdf"},
            ),
        ]

        search_result = SearchResult(
            query="test query",
            chunk_results=chunk_results,
            total_results=2,
        )
        search_service.search_documents.return_value = search_result
        return search_service

    def test_initialization(self, temp_db):
        """Test ExperimentService initialization."""
        service = ExperimentService(registry=temp_db)
        assert service.registry == temp_db
        assert service.experiments == {}

    def test_create_experiment(self, temp_db):
        """Test creating a new experiment."""
        service = ExperimentService(registry=temp_db)

        experiment = service.create_experiment(
            experiment_name="Test Experiment",
            extractor="nougat",
            embedder="chroma",
            chunk_size=1500,
            search_strategy="hybrid",
            project_id="test_project",
            description="A test experiment",
        )

        assert isinstance(experiment, ExperimentConfig)
        assert experiment.experiment_name == "Test Experiment"
        assert experiment.extractor == "nougat"
        assert experiment.embedder == "chroma"
        assert experiment.chunk_size == 1500
        assert experiment.search_strategy == "hybrid"
        assert experiment.project_id == "test_project"
        assert experiment.experiment_id.startswith("exp_")

        # Check it was stored
        assert experiment.experiment_id in service.experiments

    def test_create_experiment_defaults(self, temp_db):
        """Test creating experiment with default values."""
        service = ExperimentService(registry=temp_db)

        experiment = service.create_experiment(experiment_name="Default Test")

        assert experiment.extractor == "nougat"
        assert experiment.embedder == "chroma"
        assert experiment.chunk_size == 2000
        assert experiment.search_strategy == "semantic_only"
        assert experiment.embedder_config == {}

    def test_list_experiments(self, temp_db):
        """Test listing experiments."""
        service = ExperimentService(registry=temp_db)

        # Create multiple experiments
        service.create_experiment("Experiment 1", project_id="project_a")
        service.create_experiment("Experiment 2", project_id="project_b")
        service.create_experiment("Experiment 3", project_id="project_a")

        # List all experiments
        all_experiments = service.list_experiments()
        assert len(all_experiments) == 3

        # List experiments for specific project
        project_a_experiments = service.list_experiments(project_id="project_a")
        assert len(project_a_experiments) == 2
        assert all(exp.project_id == "project_a" for exp in project_a_experiments)

        # Should be sorted by creation date (newest first)
        assert project_a_experiments[0].created_date >= project_a_experiments[1].created_date

    def test_get_experiment(self, temp_db):
        """Test getting experiment by ID."""
        service = ExperimentService(registry=temp_db)

        experiment = service.create_experiment("Test Experiment")

        # Get existing experiment
        retrieved = service.get_experiment(experiment.experiment_id)
        assert retrieved == experiment

        # Get non-existent experiment
        assert service.get_experiment("nonexistent") is None

    def test_run_search_experiment(self, temp_db, mock_search_service):
        """Test running search experiment."""
        service = ExperimentService(registry=temp_db)

        # Create experiment
        experiment = service.create_experiment(
            "Search Test",
            embedder="chroma",
            project_id="test_project",
        )

        with patch(
            "rkb.services.experiment_service.SearchService", return_value=mock_search_service
        ):
            queries = ["machine learning", "deep learning"]
            results = service.run_search_experiment(
                experiment.experiment_id,
                queries,
                n_results=3,
            )

            assert len(results) == 2
            assert "machine learning" in results
            assert "deep learning" in results

            # Verify SearchService was called correctly
            assert mock_search_service.search_documents.call_count == 2

    def test_run_search_experiment_not_found(self, temp_db):
        """Test running search experiment with invalid ID."""
        service = ExperimentService(registry=temp_db)

        with pytest.raises(ValueError, match="Experiment nonexistent not found"):
            service.run_search_experiment("nonexistent", ["test query"])

    def test_compare_experiments(self, temp_db, mock_search_service):
        """Test comparing multiple experiments."""
        service = ExperimentService(registry=temp_db)

        # Create two experiments
        exp1 = service.create_experiment("Experiment 1", embedder="chroma")
        exp2 = service.create_experiment("Experiment 2", embedder="ollama")

        with patch(
            "rkb.services.experiment_service.SearchService", return_value=mock_search_service
        ):
            queries = ["machine learning"]
            comparison = service.compare_experiments(
                [exp1.experiment_id, exp2.experiment_id],
                queries,
                n_results=3,
            )

            assert comparison.query == "comparison_of_2_experiments"
            assert len(comparison.experiment_results) == 2
            assert exp1.experiment_id in comparison.experiment_results
            assert exp2.experiment_id in comparison.experiment_results

            # Check metrics
            assert "avg_similarity" in comparison.metrics
            assert "result_overlap" in comparison.metrics
            assert "query_coverage" in comparison.metrics

            # Each metric should have results for both experiments
            for metric_data in comparison.metrics.values():
                assert len(metric_data) == 2

    def test_compare_experiments_validation(self, temp_db):
        """Test experiment comparison validation."""
        service = ExperimentService(registry=temp_db)

        # No experiments
        with pytest.raises(ValueError, match="Must provide at least one experiment ID"):
            service.compare_experiments([], ["test"])

        # No queries
        with pytest.raises(ValueError, match="Must provide at least one test query"):
            service.compare_experiments(["exp1"], [])

        # Invalid experiment ID
        with pytest.raises(ValueError, match="Experiment invalid not found"):
            service.compare_experiments(["invalid"], ["test"])

    def test_calculate_metric_avg_similarity(self, temp_db):
        """Test calculating average similarity metric."""
        service = ExperimentService(registry=temp_db)

        # Mock experiment results
        experiment_results = {
            "exp1": {
                "query1": SearchResult(
                    query="query1",
                    chunk_results=[
                        ChunkResult("c1", "content", 0.8, 0.2, {}),
                        ChunkResult("c2", "content", 0.7, 0.3, {}),
                    ],
                    total_results=2,
                ),
                "query2": SearchResult(
                    query="query2",
                    chunk_results=[
                        ChunkResult("c3", "content", 0.9, 0.1, {}),
                    ],
                    total_results=1,
                ),
            },
        }

        metrics = service._calculate_metric(
            "avg_similarity",
            experiment_results,
            ["query1", "query2"],
        )

        # Average should be ((0.8+0.7)/2 + 0.9)/2 = 0.825
        assert metrics["exp1"] == pytest.approx(0.825, rel=1e-3)

    def test_calculate_metric_result_overlap(self, temp_db):
        """Test calculating result overlap metric."""
        service = ExperimentService(registry=temp_db)

        experiment_results = {
            "exp1": {
                "query1": SearchResult(
                    query="query1",
                    chunk_results=[
                        ChunkResult("c1", "content", 0.8, 0.2, {"doc_id": "doc1"}),
                        ChunkResult("c2", "content", 0.7, 0.3, {"doc_id": "doc2"}),
                    ],
                    total_results=2,
                ),
            },
            "exp2": {
                "query1": SearchResult(
                    query="query1",
                    chunk_results=[
                        ChunkResult("c3", "content", 0.9, 0.1, {"doc_id": "doc1"}),
                        ChunkResult("c4", "content", 0.6, 0.4, {"doc_id": "doc3"}),
                    ],
                    total_results=2,
                ),
            },
        }

        metrics = service._calculate_metric(
            "result_overlap",
            experiment_results,
            ["query1"],
        )

        # First experiment is baseline (overlap = 1.0)
        assert metrics["exp1"] == 1.0
        # Second experiment has 1 doc in common out of 2 baseline docs = 0.5
        assert metrics["exp2"] == 0.5

    def test_calculate_metric_query_coverage(self, temp_db):
        """Test calculating query coverage metric."""
        service = ExperimentService(registry=temp_db)

        experiment_results = {
            "exp1": {
                "query1": SearchResult("query1", [], 0),  # No results
                "query2": SearchResult("query2", [ChunkResult("c1", "content", 0.8, 0.2, {})], 1),
            },
        }

        metrics = service._calculate_metric(
            "query_coverage",
            experiment_results,
            ["query1", "query2"],
        )

        # Only 1 out of 2 queries returned results = 0.5
        assert metrics["exp1"] == 0.5

    def test_save_experiment_results(self, temp_db):
        """Test saving experiment results to file."""
        service = ExperimentService(registry=temp_db)

        experiment = service.create_experiment("Save Test")

        results = {
            "test query": SearchResult(
                query="test query",
                chunk_results=[
                    ChunkResult(
                        "chunk1",
                        "Long content that should be truncated" * 10,
                        0.85,
                        0.15,
                        {"doc_id": "doc1", "pdf_name": "test.pdf"},
                    ),
                ],
                total_results=1,
            ),
        }

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            output_file = Path(f.name)

        try:
            service.save_experiment_results(
                experiment.experiment_id,
                results,
                output_file,
            )

            assert output_file.exists()

            # Verify content
            import json
            with output_file.open() as f:
                data = json.load(f)

            assert data["experiment_id"] == experiment.experiment_id
            assert data["experiment_name"] == "Save Test"
            assert "configuration" in data
            assert "results" in data
            assert "test query" in data["results"]

            # Check that content was truncated
            chunk_content = data["results"]["test query"]["chunks"][0]["content"]
            assert chunk_content.endswith("...")
            assert len(chunk_content) <= 203  # 200 + "..."

        finally:
            if output_file.exists():
                output_file.unlink()

    def test_save_experiment_results_not_found(self, temp_db):
        """Test saving results for non-existent experiment."""
        service = ExperimentService(registry=temp_db)

        with pytest.raises(ValueError, match="Experiment nonexistent not found"):
            service.save_experiment_results("nonexistent", {}, "output.json")

    def test_get_experiment_summary(self, temp_db):
        """Test getting experiment summary."""
        service = ExperimentService(registry=temp_db)

        # Create experiments with different configurations
        service.create_experiment("Exp 1", embedder="chroma", extractor="nougat")
        service.create_experiment("Exp 2", embedder="ollama", extractor="nougat")
        service.create_experiment("Exp 3", embedder="chroma", extractor="pymupdf")

        summary = service.get_experiment_summary()

        assert summary["total_experiments"] == 3
        assert summary["embedder_distribution"]["chroma"] == 2
        assert summary["embedder_distribution"]["ollama"] == 1
        assert summary["extractor_distribution"]["nougat"] == 2
        assert summary["extractor_distribution"]["pymupdf"] == 1

        # Check available experiments list
        assert len(summary["available_experiments"]) == 3
        for exp_info in summary["available_experiments"]:
            assert "id" in exp_info
            assert "name" in exp_info
            assert "embedder" in exp_info
            assert "created" in exp_info
