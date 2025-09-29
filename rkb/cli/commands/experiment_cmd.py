"""Experiment command - Manage experiments and comparisons."""
# ruff: noqa: T201

import argparse
from pathlib import Path

from rkb.core.document_registry import DocumentRegistry
from rkb.services.experiment_service import ExperimentService


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add command-specific arguments."""
    subparsers = parser.add_subparsers(
        dest="action",
        help="Experiment actions",
        metavar="ACTION"
    )

    # Create experiment
    create_parser = subparsers.add_parser("create", help="Create a new experiment")
    create_parser.add_argument("name", help="Experiment name")
    create_parser.add_argument("--extractor", default="nougat", help="Extractor to use")
    create_parser.add_argument("--embedder", default="chroma", help="Embedder to use")
    create_parser.add_argument("--chunk-size", type=int, default=2000, help="Text chunk size")
    create_parser.add_argument("--search-strategy", default="semantic_only", help="Search strategy")
    create_parser.add_argument("--vector-db-path", type=Path, help="Vector database path")
    create_parser.add_argument("--project-id", help="Associated project ID")
    create_parser.add_argument("--description", help="Experiment description")

    # List experiments
    list_parser = subparsers.add_parser("list", help="List experiments")
    list_parser.add_argument("--project-id", help="Filter by project")

    # Run experiment
    run_parser = subparsers.add_parser("run", help="Run search experiment")
    run_parser.add_argument("experiment_id", help="Experiment ID")
    run_parser.add_argument("queries", nargs="+", help="Search queries")
    run_parser.add_argument("--num-results", type=int, default=5, help="Results per query")

    # Compare experiments
    compare_parser = subparsers.add_parser("compare", help="Compare experiments")
    compare_parser.add_argument("experiment_ids", nargs="+", help="Experiment IDs to compare")
    compare_parser.add_argument("--queries", nargs="+", required=True, help="Test queries")
    compare_parser.add_argument("--num-results", type=int, default=5, help="Results per query")

    # Show summary
    subparsers.add_parser("summary", help="Show experiment summary")

    # Global options
    parser.add_argument(
        "--db-path",
        type=Path,
        default="rkb_documents.db",
        help="Path to document registry database (default: rkb_documents.db)"
    )


def execute(args: argparse.Namespace) -> int:
    """Execute the experiment command."""
    if not args.action:
        print("Error: No action specified. Use --help for available actions.")
        return 1

    try:
        # Initialize services
        registry = DocumentRegistry(args.db_path)
        experiment_service = ExperimentService(registry)

        if args.action == "create":
            return _create_experiment(experiment_service, args)
        if args.action == "list":
            return _list_experiments(experiment_service, args)
        if args.action == "run":
            return _run_experiment(experiment_service, args)
        if args.action == "compare":
            return _compare_experiments(experiment_service, args)
        if args.action == "summary":
            return _show_summary(experiment_service, args)
        print(f"Unknown action: {args.action}")
        return 1

    except Exception as e:
        print(f"✗ Experiment command failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def _create_experiment(service: ExperimentService, args: argparse.Namespace) -> int:
    """Create a new experiment."""
    experiment = service.create_experiment(
        experiment_name=args.name,
        extractor=args.extractor,
        embedder=args.embedder,
        chunk_size=args.chunk_size,
        search_strategy=args.search_strategy,
        vector_db_path=args.vector_db_path,
        project_id=args.project_id,
        description=args.description or ""
    )
    print(f"Experiment ID: {experiment.experiment_id}")
    return 0


def _list_experiments(service: ExperimentService, args: argparse.Namespace) -> int:
    """List experiments."""
    experiments = service.list_experiments(project_id=args.project_id)

    if not experiments:
        print("No experiments found.")
        return 0

    print("🧪 Experiments")
    print("=" * 50)
    for exp in experiments:
        print(f"\nID: {exp.experiment_id}")
        print(f"Name: {exp.experiment_name}")
        print(f"Embedder: {exp.embedder}")
        print(f"Extractor: {exp.extractor}")
        print(f"Strategy: {exp.search_strategy}")
        print(f"Created: {exp.created_date.strftime('%Y-%m-%d %H:%M')}")

    return 0


def _run_experiment(service: ExperimentService, args: argparse.Namespace) -> int:
    """Run search experiment."""
    try:
        results = service.run_search_experiment(
            experiment_id=args.experiment_id,
            queries=args.queries,
            n_results=args.num_results
        )

        print("\n📊 Experiment Results")
        print("=" * 40)
        for query, result in results.items():
            print(f"\nQuery: '{query}'")
            print(f"Results: {result.total_results}")
            if result.chunk_results:
                print(f"Avg similarity: {result.avg_score:.3f}")

        return 0
    except Exception as e:
        print(f"✗ Error running experiment: {e}")
        return 1


def _compare_experiments(service: ExperimentService, args: argparse.Namespace) -> int:
    """Compare experiments."""
    try:
        comparison = service.compare_experiments(
            experiment_ids=args.experiment_ids,
            test_queries=args.queries,
            n_results=args.num_results
        )

        print("📈 Comparison completed successfully")
        return 0
    except Exception as e:
        print(f"✗ Error comparing experiments: {e}")
        return 1


def _show_summary(service: ExperimentService, args: argparse.Namespace) -> int:
    """Show experiment summary."""
    summary = service.get_experiment_summary()

    print("🧪 Experiment Summary")
    print("=" * 30)
    print(f"Total experiments: {summary['total_experiments']}")

    if summary["embedder_distribution"]:
        print("\nEmbedder distribution:")
        for embedder, count in summary["embedder_distribution"].items():
            print(f"  {embedder}: {count}")

    if summary["extractor_distribution"]:
        print("\nExtractor distribution:")
        for extractor, count in summary["extractor_distribution"].items():
            print(f"  {extractor}: {count}")

    return 0
