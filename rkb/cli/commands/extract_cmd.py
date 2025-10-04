"""Extract command - Extract content from PDF documents."""
# ruff: noqa: T201

import argparse
from pathlib import Path

from rkb.core.document_registry import DocumentRegistry
from rkb.pipelines.ingestion_pipeline import IngestionPipeline


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add command-specific arguments."""
    parser.add_argument("files", nargs="+", type=Path, help="PDF files to extract")

    parser.add_argument(
        "--extractor",
        choices=["nougat"],
        default="nougat",
        help="Extractor to use (default: nougat)",
    )

    parser.add_argument(
        "--max-pages", type=int, default=500, help="Maximum pages per PDF (default: 500)"
    )

    parser.add_argument("--project-id", help="Project ID to associate documents with")

    parser.add_argument(
        "--force-reprocess", action="store_true", help="Force reprocessing of existing documents"
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        default=True,
        help="Resume from checkpoint if available (default: True)",
    )

    parser.add_argument("--no-resume", action="store_true", help="Do not resume from checkpoint")

    parser.add_argument(
        "--checkpoint-dir", type=Path, help="Directory for checkpoint files (default: .checkpoints)"
    )

    parser.add_argument(
        "--db-path",
        type=Path,
        default="rkb_documents.db",
        help="Path to document registry database (default: rkb_documents.db)",
    )

    parser.add_argument(
        "--extraction-dir",
        type=Path,
        default=Path("rkb_extractions"),
        help="Directory for extraction output (default: rkb_extractions)",
    )


def execute(args: argparse.Namespace) -> int:
    """Execute the extract command."""
    try:
        # Validate files
        pdf_files = []
        for file_path in args.files:
            if not file_path.exists():
                print(f"✗ File not found: {file_path}")
                return 1
            if file_path.suffix.lower() != ".pdf":
                print(f"✗ Not a PDF file: {file_path}")
                return 1
            pdf_files.append(file_path)

        print(f"📄 Extracting content from {len(pdf_files)} PDF files")
        print(f"⚙️  Extractor: {args.extractor}")
        print(f"📖 Max pages: {args.max_pages}")
        print()

        # Initialize services
        registry = DocumentRegistry(args.db_path)

        # Determine checkpoint directory
        checkpoint_dir = (
            args.checkpoint_dir if hasattr(args, "checkpoint_dir") and args.checkpoint_dir else None
        )

        pipeline = IngestionPipeline(
            registry=registry,
            extractor_name=args.extractor,
            project_id=args.project_id,
            skip_embedding=True,  # Only extract, don't embed
            checkpoint_dir=checkpoint_dir,
            extraction_dir=args.extraction_dir,
        )

        # Determine resume flag
        resume = not args.no_resume if hasattr(args, "no_resume") else True

        # Process files
        pdf_list = [str(path) for path in pdf_files]
        results = pipeline.process_batch(
            pdf_list=pdf_list,
            max_files=len(pdf_files),
            force_reprocess=args.force_reprocess,
            resume=resume,
        )

        # Display results
        print("=" * 50)
        print("🎉 EXTRACTION COMPLETED")
        print("=" * 50)

        # Count results by status
        successful = len([r for r in results if r.get("status") == "success"])
        failed = len([r for r in results if r.get("status") == "error"])
        skipped = len([r for r in results if r.get("status") == "skipped"])

        print(f"📄 Documents processed: {len(results)}")
        print(f"✅ Successful extractions: {successful}")
        print(f"❌ Failed extractions: {failed}")
        print(f"⏭️  Skipped: {skipped}")

        if successful > 0:
            print("\n✨ Extraction complete! Documents status: EXTRACTED")
            print("To create embeddings and enable search, run: rkb index")
            if args.project_id:
                print(f"Or run: rkb index --project-id {args.project_id}")

        return 0

    except Exception as e:
        print(f"✗ Extract command failed: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1
