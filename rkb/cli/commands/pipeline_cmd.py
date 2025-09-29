"""Pipeline command - Run complete PDF processing pipeline."""

import argparse
import time
from datetime import datetime
from pathlib import Path

from rkb.core.document_registry import DocumentRegistry
from rkb.pipelines.complete_pipeline import CompletePipeline
from rkb.services.project_service import ProjectService


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add command-specific arguments."""
    parser.add_argument(
        "--data-dir",
        type=Path,
        default="data/initial",
        help="Directory containing PDF files (default: data/initial)"
    )

    parser.add_argument(
        "--num-files",
        type=int,
        default=50,
        help="Number of recent files to process (default: 50)"
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=15,
        help="Maximum pages per PDF to process (default: 15)"
    )

    parser.add_argument(
        "--extractor",
        choices=["nougat"],
        default="nougat",
        help="Extractor to use (default: nougat)"
    )

    parser.add_argument(
        "--embedder",
        choices=["chroma", "ollama"],
        default="chroma",
        help="Embedder to use (default: chroma)"
    )

    parser.add_argument(
        "--project-id",
        type=str,
        help="Project ID to associate documents with"
    )

    parser.add_argument(
        "--project-name",
        type=str,
        help="Create new project with this name"
    )

    parser.add_argument(
        "--db-path",
        type=Path,
        default="rkb_documents.db",
        help="Path to document registry database (default: rkb_documents.db)"
    )

    parser.add_argument(
        "--vector-db-path",
        type=Path,
        default="rkb_chroma_db",
        help="Path to vector database (default: rkb_chroma_db)"
    )

    parser.add_argument(
        "--force-reprocess",
        action="store_true",
        help="Force reprocessing of existing documents"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without actually processing"
    )


def execute(args: argparse.Namespace) -> int:
    """Execute the pipeline command."""
    print("🚀 RKB PDF Processing Pipeline")
    print("=" * 50)
    print(f"📁 Source directory: {args.data_dir}")
    print(f"📄 Number of files: {args.num_files}")
    print(f"📖 Max pages per PDF: {args.max_pages}")
    print(f"🔄 Force reprocess: {args.force_reprocess}")
    print(f"🧪 Dry run: {args.dry_run}")
    print(f"⚙️  Extractor: {args.extractor}")
    print(f"🔗 Embedder: {args.embedder}")
    print()

    start_time = time.time()

    try:
        # Initialize registry
        registry = DocumentRegistry(args.db_path)

        # Handle project creation/selection
        project_id = args.project_id
        if args.project_name:
            project_service = ProjectService(registry)
            project_id = project_service.create_project(
                project_name=args.project_name,
                description=f"Pipeline run on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                data_dir=args.data_dir
            )
            print(f"✓ Created project: {project_id}")
            print()

        # Validate data directory
        if not args.data_dir.exists():
            print(f"✗ Data directory not found: {args.data_dir}")
            return 1

        # Find recent PDFs first
        project_service = ProjectService(registry)
        print("📋 Step 1: Finding recent PDFs...")

        try:
            recent_files = project_service.find_recent_pdfs(
                data_dir=args.data_dir,
                num_files=args.num_files,
                project_id=project_id
            )

            if not recent_files:
                print("✗ No PDFs found. Check data directory.")
                return 1

            print(f"✓ Found {len(recent_files)} recent PDFs")

            if args.dry_run:
                print("\n🔍 Files that would be processed:")
                for i, file_info in enumerate(recent_files[:10], 1):
                    print(f"  {i:2d}. {file_info['name']} ({file_info['size_mb']:.1f} MB)")
                if len(recent_files) > 10:
                    print(f"  ... and {len(recent_files) - 10} more files")
                return 0

        except Exception as e:
            print(f"✗ Error finding PDFs: {e}")
            return 1

        print()

        # Step 2: Initialize and run pipeline
        print("🔄 Step 2: Running processing pipeline...")

        pipeline = CompletePipeline(
            registry=registry,
            extractor_name=args.extractor,
            embedder_name=args.embedder,
            project_id=project_id
        )

        # Process documents using run_pipeline
        results = pipeline.run_pipeline(
            data_dir=args.data_dir,
            num_files=args.num_files,
            max_pages=args.max_pages,
            force_reprocess=args.force_reprocess,
            test_mode=False
        )

        # Display results
        elapsed_time = time.time() - start_time

        print("\n" + "=" * 50)
        print("🎉 PIPELINE COMPLETED")
        print("=" * 50)
        print(f"⏱️  Total time: {elapsed_time:.1f} seconds")
        print(f"📄 Documents processed: {results['documents_processed']}")
        print(f"✅ Successfully processed: {results['successful_extractions']}")
        print(f"❌ Failed extractions: {results['failed_extractions']}")
        print(f"🔗 Documents indexed: {results['successful_embeddings']}")
        print(f"❌ Failed indexing: {results['failed_embeddings']}")

        if results["successful_embeddings"] > 0:
            print("\n🔍 Ready for semantic search!")
            print('   Run: rkb search "your query here"')

        if project_id:
            print(f"📁 Project ID: {project_id}")

        return 0

    except KeyboardInterrupt:
        print("\n⏹️  Pipeline interrupted by user")
        return 130
    except Exception as e:
        print(f"\n✗ Pipeline failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1
