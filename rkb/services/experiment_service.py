"""Experiment service for managing and comparing different configurations."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from rkb.core.document_registry import DocumentRegistry
from rkb.core.models import ComparisonResult, ExperimentConfig, SearchResult
from rkb.services.search_service import SearchService

LOGGER = logging.getLogger("rkb.services.experiment_service")


class ExperimentService:
    """Service for managing experiments and comparing different configurations."""

    def __init__(self, registry: DocumentRegistry | None = None):
        """Initialize experiment service.

        Args:
            registry: Document registry for experiment tracking
        """
        self.registry = registry or DocumentRegistry()
        self.experiments = {}  # In-memory storage, could be persisted later

    def create_experiment(
        self,
        experiment_name: str,
        extractor: str = "nougat",
        embedder: str = "chroma",
        embedder_config: dict[str, Any] | None = None,
        chunk_size: int = 2000,
        search_strategy: str = "semantic_only",
        vector_db_path: str | Path | None = None,
        project_id: str | None = None,
        description: str = "",
    ) -> ExperimentConfig:
        """Create a new experiment configuration.

        Args:
            experiment_name: Name for the experiment
            extractor: Extractor to use
            embedder: Embedder to use
            embedder_config: Configuration for the embedder
            chunk_size: Text chunk size
            search_strategy: Search strategy to use
            vector_db_path: Path to vector database
            project_id: Associated project ID
            description: Experiment description

        Returns:
            ExperimentConfig object
        """
        experiment_config = ExperimentConfig(
            experiment_name=experiment_name,
            project_id=project_id,
            extractor=extractor,
            embedder=embedder,
            embedder_config=embedder_config or {},
            chunk_size=chunk_size,
            search_strategy=search_strategy,
            vector_db_path=Path(vector_db_path) if vector_db_path else None,
        )

        # Store experiment configuration
        self.experiments[experiment_config.experiment_id] = experiment_config

        exp_id = experiment_config.experiment_id
        LOGGER.info(f"Created experiment '{experiment_name}' with ID: {exp_id}")
        LOGGER.debug(f"  Extractor: {extractor}")
        LOGGER.debug(f"  Embedder: {embedder}")
        LOGGER.debug(f"  Chunk size: {chunk_size}")
        LOGGER.debug(f"  Search strategy: {search_strategy}")

        return experiment_config

    def list_experiments(self, project_id: str | None = None) -> list[ExperimentConfig]:
        """List all experiments, optionally filtered by project.

        Args:
            project_id: Optional project ID filter

        Returns:
            List of experiment configurations
        """
        experiments = list(self.experiments.values())

        if project_id:
            experiments = [exp for exp in experiments if exp.project_id == project_id]

        # Sort by creation date
        experiments.sort(key=lambda x: x.created_date, reverse=True)

        return experiments

    def get_experiment(self, experiment_id: str) -> ExperimentConfig | None:
        """Get experiment configuration by ID.

        Args:
            experiment_id: Experiment identifier

        Returns:
            ExperimentConfig if found, None otherwise
        """
        return self.experiments.get(experiment_id)

    def run_search_experiment(
        self,
        experiment_id: str,
        queries: list[str],
        n_results: int = 5,
    ) -> dict[str, SearchResult]:
        """Run search queries using an experiment configuration.

        Args:
            experiment_id: Experiment to use
            queries: List of search queries
            n_results: Number of results per query

        Returns:
            Dictionary mapping queries to search results
        """
        experiment = self.get_experiment(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment {experiment_id} not found")

        LOGGER.info(f"Running search experiment: {experiment.experiment_name}")
        LOGGER.debug(f"   Queries: {len(queries)}")
        config_msg = f"{experiment.embedder} embedder, {experiment.search_strategy} strategy"
        LOGGER.debug(f"   Configuration: {config_msg}")

        # Initialize search service with experiment configuration
        search_service = SearchService(
            db_path=experiment.vector_db_path or "rkb_chroma_db",
            collection_name="documents",
            embedder_name=experiment.embedder,
            registry=self.registry,
        )

        results = {}
        for query in queries:
            LOGGER.debug(f"  Searching: {query}")
            search_result = search_service.search_documents(
                query=query,
                n_results=n_results,
                project_id=experiment.project_id,
            )
            results[query] = search_result

        LOGGER.info(f"Completed search experiment with {len(results)} queries")
        return results

    def compare_experiments(
        self,
        experiment_ids: list[str],
        test_queries: list[str],
        n_results: int = 5,
        metrics: list[str] | None = None,
    ) -> ComparisonResult:
        """Compare multiple experiments using the same test queries.

        Args:
            experiment_ids: List of experiment IDs to compare
            test_queries: Queries to test with
            n_results: Number of results per query
            metrics: Metrics to calculate (similarity, coverage, etc.)

        Returns:
            ComparisonResult with analysis
        """
        if not experiment_ids:
            raise ValueError("Must provide at least one experiment ID")

        if not test_queries:
            raise ValueError("Must provide at least one test query")

        LOGGER.info(f"Comparing {len(experiment_ids)} experiments on {len(test_queries)} queries")

        # Get experiment configurations
        experiments = {}
        for exp_id in experiment_ids:
            exp = self.get_experiment(exp_id)
            if not exp:
                raise ValueError(f"Experiment {exp_id} not found")
            experiments[exp_id] = exp
            LOGGER.debug(f"  - {exp.experiment_name}: {exp.embedder} embedder")

        # Run experiments
        experiment_results = {}
        for exp_id, experiment in experiments.items():
            LOGGER.info(f"Running experiment: {experiment.experiment_name}")
            results = self.run_search_experiment(exp_id, test_queries, n_results)
            experiment_results[exp_id] = results

        # Calculate metrics
        metrics_data = {}
        if not metrics:
            metrics = ["avg_similarity", "result_overlap", "query_coverage"]

        for metric in metrics:
            metrics_data[metric] = self._calculate_metric(
                metric, experiment_results, test_queries
            )

        comparison_result = ComparisonResult(
            query=f"comparison_of_{len(experiment_ids)}_experiments",
            experiment_results=experiment_results,
            metrics=metrics_data,
        )

        LOGGER.info("Comparison completed")
        self._display_comparison_summary(comparison_result, experiments)

        return comparison_result

    def _calculate_metric(
        self,
        metric: str,
        experiment_results: dict[str, dict[str, SearchResult]],
        test_queries: list[str],
    ) -> dict[str, float]:
        """Calculate a specific metric across experiments.

        Args:
            metric: Metric name to calculate
            experiment_results: Results from all experiments
            test_queries: List of test queries

        Returns:
            Dictionary mapping experiment IDs to metric values
        """
        metric_values = {}

        for exp_id, exp_results in experiment_results.items():
            if metric == "avg_similarity":
                # Average similarity across all queries
                similarities = []
                for query in test_queries:
                    if query in exp_results and exp_results[query].chunk_results:
                        avg_sim = exp_results[query].avg_score
                        similarities.append(avg_sim)
                avg_similarity = sum(similarities) / len(similarities) if similarities else 0.0
                metric_values[exp_id] = avg_similarity

            elif metric == "result_overlap":
                # Measure overlap with first experiment (baseline)
                if not metric_values:  # First experiment becomes baseline
                    metric_values[exp_id] = 1.0
                else:
                    baseline_exp_id = list(experiment_results.keys())[0]
                    baseline_results = experiment_results[baseline_exp_id]

                    overlaps = []
                    for query in test_queries:
                        if query in exp_results and query in baseline_results:
                            current_docs = {
                                chunk.metadata.get("doc_id")
                                for chunk in exp_results[query].chunk_results
                            }
                            baseline_docs = {
                                chunk.metadata.get("doc_id")
                                for chunk in baseline_results[query].chunk_results
                            }

                            if baseline_docs:
                                overlap = len(current_docs & baseline_docs) / len(baseline_docs)
                                overlaps.append(overlap)

                    metric_values[exp_id] = sum(overlaps) / len(overlaps) if overlaps else 0.0

            elif metric == "query_coverage":
                # Percentage of queries that returned results
                successful_queries = sum(
                    1 for query in test_queries
                    if query in exp_results and exp_results[query].total_results > 0
                )
                metric_values[exp_id] = successful_queries / len(test_queries)

        return metric_values

    def _display_comparison_summary(
        self,
        comparison: ComparisonResult,
        experiments: dict[str, ExperimentConfig],
    ) -> None:
        """Display a summary of the comparison results.

        Args:
            comparison: ComparisonResult to display
            experiments: Dictionary of experiment configurations
        """
        LOGGER.info("=" * 80)
        LOGGER.info("EXPERIMENT COMPARISON SUMMARY")
        LOGGER.info("=" * 80)

        # Show experiment details
        for exp_id, exp in experiments.items():
            LOGGER.info(f"{exp.experiment_name} ({exp_id}):")
            LOGGER.info(f"  Embedder: {exp.embedder}")
            LOGGER.info(f"  Chunk size: {exp.chunk_size}")
            LOGGER.info(f"  Strategy: {exp.search_strategy}")

        # Show metrics
        LOGGER.info("METRICS:")
        for metric_name, metric_data in comparison.metrics.items():
            LOGGER.info(f"{metric_name.replace('_', ' ').title()}:")
            sorted_results = sorted(metric_data.items(), key=lambda x: x[1], reverse=True)
            for exp_id, value in sorted_results:
                exp_name = experiments[exp_id].experiment_name
                LOGGER.info(f"  {exp_name}: {value:.3f}")

        LOGGER.info("=" * 80)

    def save_experiment_results(
        self,
        experiment_id: str,
        results: dict[str, SearchResult],
        output_file: str | Path,
    ) -> None:
        """Save experiment results to file.

        Args:
            experiment_id: Experiment identifier
            results: Search results from experiment
            output_file: Path to save results
        """
        experiment = self.get_experiment(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment {experiment_id} not found")

        output_data = {
            "experiment_id": experiment_id,
            "experiment_name": experiment.experiment_name,
            "configuration": {
                "extractor": experiment.extractor,
                "embedder": experiment.embedder,
                "chunk_size": experiment.chunk_size,
                "search_strategy": experiment.search_strategy,
            },
            "timestamp": datetime.now().isoformat(),
            "results": {},
        }

        # Convert SearchResults to serializable format
        for query, search_result in results.items():
            output_data["results"][query] = {
                "total_results": search_result.total_results,
                "avg_similarity": search_result.avg_score,
                "chunks": [
                    {
                        "content": (
                            (
                                chunk.content[:200] + "..."
                                if len(chunk.content) > 200
                                else chunk.content
                            )
                        ),
                        "similarity": chunk.similarity,
                        "metadata": chunk.metadata,
                    }
                    for chunk in search_result.chunk_results
                ],
            }

        # Save to file
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w") as f:
            json.dump(output_data, f, indent=2)

        LOGGER.info(f"Saved experiment results to: {output_path}")

    def get_experiment_summary(self) -> dict[str, Any]:
        """Get summary of all experiments.

        Returns:
            Dictionary with experiment statistics
        """
        total_experiments = len(self.experiments)

        # Group by embedder
        embedder_counts = {}
        extractor_counts = {}

        for exp in self.experiments.values():
            embedder_counts[exp.embedder] = embedder_counts.get(exp.embedder, 0) + 1
            extractor_counts[exp.extractor] = extractor_counts.get(exp.extractor, 0) + 1

        return {
            "total_experiments": total_experiments,
            "embedder_distribution": embedder_counts,
            "extractor_distribution": extractor_counts,
            "available_experiments": [
                {
                    "id": exp.experiment_id,
                    "name": exp.experiment_name,
                    "embedder": exp.embedder,
                    "created": exp.created_date.isoformat(),
                }
                for exp in self.experiments.values()
            ],
        }
