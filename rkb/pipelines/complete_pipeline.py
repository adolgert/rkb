"""Complete pipeline for document discovery, processing, and indexing."""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rkb.core.document_registry import DocumentRegistry
from rkb.core.models import DocumentStatus
from rkb.pipelines.ingestion_pipeline import IngestionPipeline

LOGGER = logging.getLogger("rkb.pipelines.complete_pipeline")


class CompletePipeline:
    """Complete pipeline orchestrating document discovery and processing."""

    def __init__(
        self,
        registry: DocumentRegistry | None = None,
        extractor_name: str = "nougat",
        embedder_name: str = "chroma",
        project_id: str | None = None,
    ):
        """Initialize complete pipeline.

        Args:
            registry: Document registry for tracking documents
            extractor_name: Name of extractor to use
            embedder_name: Name of embedder to use
            project_id: Project identifier for document organization
        """
        self.registry = registry or DocumentRegistry()
        self.project_id = project_id or f"project_{int(time.time())}"

        # Initialize ingestion pipeline
        self.ingestion_pipeline = IngestionPipeline(
            registry=self.registry,
            extractor_name=extractor_name,
            embedder_name=embedder_name,
            project_id=self.project_id,
        )

    def find_recent_pdfs(
        self,
        data_dir: str | Path = "data/initial",
        num_files: int = 50,
        output_file: str | Path | None = None,
    ) -> list[dict[str, Any]]:
        """Find the most recent PDF files based on modification time.

        Args:
            data_dir: Directory to search for PDFs
            num_files: Maximum number of files to return
            output_file: Optional path to save file list as JSON

        Returns:
            List of file information dictionaries
        """
        data_path = Path(data_dir)
        if not data_path.exists():
            raise FileNotFoundError(f"Data directory not found: {data_path}")

        LOGGER.info(f"Scanning for PDFs in: {data_path}")

        # Find all PDF files
        pdf_files = list(data_path.glob("*.pdf"))

        if not pdf_files:
            raise FileNotFoundError(f"No PDF files found in {data_path}")

        LOGGER.info(f"Found {len(pdf_files)} PDF files")

        # Get file info with modification time
        file_info = []
        for pdf_file in pdf_files:
            try:
                stat = pdf_file.stat()
                file_info.append({
                    "path": str(pdf_file),
                    "name": pdf_file.name,
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "modified_time": stat.st_mtime,
                    "modified_date": datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                })
            except Exception as e:
                LOGGER.warning(f"Error reading {pdf_file}: {e}")
                continue

        # Sort by modification time (most recent first)
        file_info.sort(key=lambda x: x["modified_time"], reverse=True)

        # Take the most recent files
        recent_files = file_info[:num_files]

        LOGGER.info(f"Selected {len(recent_files)} most recent files:")
        if recent_files:
            newest = recent_files[0]
            LOGGER.debug(f"   Newest: {newest['name']} ({newest['modified_date']})")
            if len(recent_files) > 1:
                oldest = recent_files[-1]
                LOGGER.debug(f"   Oldest: {oldest['name']} ({oldest['modified_date']})")

        # Calculate total size
        total_size = sum(file["size_mb"] for file in recent_files)
        LOGGER.info(f"Total size: {total_size:.1f} MB")

        # Save to JSON file if requested
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with output_path.open("w") as f:
                json.dump(recent_files, f, indent=2)

            LOGGER.info(f"Saved file list to: {output_path}")

        return recent_files

    def run_pipeline(
        self,
        data_dir: str | Path = "data/initial",
        num_files: int = 50,
        max_pages: int = 15,
        max_chunk_size: int = 2000,
        force_reprocess: bool = False,
        test_mode: bool = True,
        log_file: str | Path | None = None,
    ) -> dict[str, Any]:
        """Run the complete PDF processing pipeline.

        Args:
            data_dir: Directory containing PDF files
            num_files: Maximum number of files to process
            max_pages: Maximum pages per PDF to process
            max_chunk_size: Maximum size for text chunks
            force_reprocess: Whether to reprocess existing documents
            test_mode: Whether to run in test mode with reduced processing
            log_file: Optional path to save processing log

        Returns:
            Dictionary with pipeline results and statistics
        """
        LOGGER.info("RKB Complete Processing Pipeline")
        LOGGER.info("=" * 50)
        LOGGER.info(f"Source directory: {data_dir}")
        LOGGER.info(f"Number of files: {num_files}")
        LOGGER.info(f"Max pages per PDF: {max_pages}")
        LOGGER.info(f"Force reprocess: {force_reprocess}")
        LOGGER.info(f"Test mode: {test_mode}")
        LOGGER.info(f"Project ID: {self.project_id}")

        start_time = time.time()
        pipeline_results = {
            "pipeline_config": {
                "data_dir": str(data_dir),
                "num_files": num_files,
                "max_pages": max_pages,
                "max_chunk_size": max_chunk_size,
                "force_reprocess": force_reprocess,
                "test_mode": test_mode,
                "project_id": self.project_id,
                "extractor": self.ingestion_pipeline.extractor_name,
                "embedder": self.ingestion_pipeline.embedder_name,
            },
            "steps": {},
            "success": False,
        }

        try:
            # Step 1: Find recent PDFs
            LOGGER.info("Step 1: Finding recent PDFs...")
            try:
                recent_files = self.find_recent_pdfs(
                    data_dir=data_dir,
                    num_files=num_files,
                )

                if not recent_files:
                    raise ValueError("No PDFs found")

                pipeline_results["steps"]["find_files"] = {
                    "success": True,
                    "files_found": len(recent_files),
                    "total_size_mb": sum(f["size_mb"] for f in recent_files),
                }

                LOGGER.info(f"Found {len(recent_files)} recent PDFs")

            except Exception as e:
                pipeline_results["steps"]["find_files"] = {
                    "success": False,
                    "error": str(e),
                }
                LOGGER.error(f"Error finding PDFs: {e}")
                return pipeline_results

            # Step 2: Process documents through ingestion pipeline
            LOGGER.info("Step 2: Processing documents through ingestion pipeline...")
            try:
                # Limit files in test mode
                files_to_process = recent_files[:3] if test_mode else recent_files

                processing_results = self.ingestion_pipeline.process_batch(
                    pdf_list=files_to_process,
                    force_reprocess=force_reprocess,
                    max_chunk_size=max_chunk_size,
                    log_file=log_file,
                )

                # Count successes and failures
                success_count = sum(1 for r in processing_results if r["status"] == "success")
                error_count = sum(1 for r in processing_results if r["status"] == "error")
                skip_count = sum(1 for r in processing_results if r["status"] == "skipped")

                pipeline_results["steps"]["process_documents"] = {
                    "success": success_count > 0,
                    "total_files": len(files_to_process),
                    "successful": success_count,
                    "errors": error_count,
                    "skipped": skip_count,
                    "results": processing_results,
                }

                if success_count == 0:
                    raise ValueError("No successful document processing")

                LOGGER.info(f"Processed {success_count}/{len(files_to_process)} documents")

            except Exception as e:
                pipeline_results["steps"]["process_documents"] = {
                    "success": False,
                    "error": str(e),
                }
                LOGGER.error(f"Error during document processing: {e}")
                return pipeline_results

            # Step 3: Get processing statistics
            LOGGER.info("Step 3: Gathering processing statistics...")
            try:
                stats = self.ingestion_pipeline.get_processing_stats()
                pipeline_results["steps"]["statistics"] = {
                    "success": True,
                    "stats": stats,
                }

                LOGGER.info("Pipeline statistics gathered")
                LOGGER.debug(f"   Total documents: {stats['total_documents']}")
                LOGGER.debug(f"   Total extractions: {stats['total_extractions']}")
                LOGGER.debug(f"   Total embeddings: {stats['total_embeddings']}")
                LOGGER.debug(f"   Total chunks: {stats['total_chunks_embedded']}")

            except Exception as e:
                pipeline_results["steps"]["statistics"] = {
                    "success": False,
                    "error": str(e),
                }
                LOGGER.warning(f"Error gathering statistics: {e}")

            # Pipeline completion
            end_time = time.time()
            duration = end_time - start_time

            # Calculate statistics for CLI compatibility
            proc_stats = pipeline_results["steps"]["process_documents"]
            total_processed = proc_stats["total_files"]
            successful_extractions = proc_stats["successful"]
            failed_extractions = proc_stats["errors"]

            # Count embeddings from processing results
            successful_embeddings = 0
            failed_embeddings = 0
            for result in proc_stats.get("results", []):
                if result.get("status") == "success" and not result.get("embedding_skipped", False):
                    successful_embeddings += 1
                elif result.get("status") == "success" and result.get("embedding_skipped", False):
                    # Extraction succeeded but embedding was skipped
                    pass
                elif result.get("status") == "error":
                    # Could be extraction or embedding failure - need more granular tracking
                    failed_embeddings += 1

            pipeline_results.update({
                "success": True,
                "duration_seconds": round(duration, 1),
                "timestamp": datetime.now().isoformat(),
                # Add CLI-expected keys
                "documents_processed": total_processed,
                "successful_extractions": successful_extractions,
                "failed_extractions": failed_extractions,
                "successful_embeddings": successful_embeddings,
                "failed_embeddings": failed_embeddings,
            })

            # Print summary
            LOGGER.info("Pipeline Summary")
            LOGGER.info("=" * 50)
            LOGGER.info(f"Total time: {duration:.1f} seconds")
            LOGGER.info(f"Files found: {pipeline_results['steps']['find_files']['files_found']}")

            LOGGER.info(f"Documents processed: {successful_extractions}/{total_processed}")
            if failed_extractions > 0:
                LOGGER.warning(f"Processing errors: {failed_extractions}")
            if proc_stats["skipped"] > 0:
                LOGGER.info(f"Skipped: {proc_stats['skipped']}")

            stats_step = pipeline_results["steps"].get("statistics", {})
            if "statistics" in pipeline_results["steps"] and stats_step["success"]:
                stats = pipeline_results["steps"]["statistics"]["stats"]
                LOGGER.info(f"Total chunks indexed: {stats['total_chunks_embedded']}")

            LOGGER.info(f"Project ID: {self.project_id}")
            LOGGER.info("Ready for semantic search!")

            return pipeline_results

        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time

            pipeline_results.update({
                "success": False,
                "duration_seconds": round(duration, 1),
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
                # Add CLI-expected keys with zero values
                "documents_processed": 0,
                "successful_extractions": 0,
                "failed_extractions": 0,
                "successful_embeddings": 0,
                "failed_embeddings": 0,
            })

            LOGGER.error(f"Pipeline failed after {duration:.1f} seconds: {e}")
            return pipeline_results

    def validate_prerequisites(self, data_dir: str | Path = "data/initial") -> bool:
        """Check that all required components are available.

        Args:
            data_dir: Directory to check for PDF files

        Returns:
            True if all prerequisites are met
        """
        LOGGER.info("🔧 Checking prerequisites...")

        # Check data directory
        data_path = Path(data_dir)
        if not data_path.exists():
            LOGGER.error(f"✗ Data directory not found: {data_path}")
            return False

        pdf_count = len(list(data_path.glob("*.pdf")))
        if pdf_count == 0:
            LOGGER.error(f"✗ No PDF files found in {data_path}")
            return False

        LOGGER.info(f"✓ Found {pdf_count} PDFs in data directory")

        # Check extractor
        try:
            extractor = self.ingestion_pipeline.extractor
            capabilities = extractor.get_capabilities()
            LOGGER.info(f"✓ Extractor '{extractor.name}' is available")
        except Exception as e:
            LOGGER.error(f"✗ Extractor check failed: {e}")
            return False

        # Check embedder
        try:
            embedder = self.ingestion_pipeline.embedder
            capabilities = embedder.get_capabilities()
            LOGGER.info(f"✓ Embedder '{embedder.name}' is available")
        except Exception as e:
            LOGGER.error(f"✗ Embedder check failed: {e}")
            return False

        # Test database connectivity
        try:
            stats = self.registry.get_processing_stats()
            LOGGER.info("✓ Document registry is functional")
        except Exception as e:
            LOGGER.error(f"✗ Document registry check failed: {e}")
            return False

        return True

    def get_project_summary(self) -> dict[str, Any]:
        """Get summary of project processing status.

        Returns:
            Dictionary with project summary information
        """
        stats = self.ingestion_pipeline.get_processing_stats()
        documents = self.ingestion_pipeline.list_documents()

        return {
            "project_id": self.project_id,
            "total_documents": len(documents),
            "processing_stats": stats,
            "extractor": self.ingestion_pipeline.extractor_name,
            "embedder": self.ingestion_pipeline.embedder_name,
            "registry_db": str(self.registry.db_path),
        }

    def process_documents(
        self,
        pdf_paths: list[Path],
        project_id: str | None = None,
        force_reprocess: bool = False,
        skip_extraction: bool = False,
    ) -> dict[str, Any]:
        """Process documents with optional extraction skipping for indexing-only.

        Args:
            pdf_paths: List of PDF paths to process
            project_id: Project identifier
            force_reprocess: Whether to reprocess existing documents
            skip_extraction: If True, only perform embedding/indexing

        Returns:
            Dictionary with processing results
        """
        if skip_extraction:
            # For indexing-only, we need to create a pipeline that only does embedding
            embedding_pipeline = IngestionPipeline(
                registry=self.registry,
                extractor_name=self.ingestion_pipeline.extractor_name,
                embedder_name=self.ingestion_pipeline.embedder_name,
                project_id=project_id or self.project_id,
                skip_embedding=False  # We want embedding for indexing
            )

            # Process only documents that are already extracted
            results = []
            successful_embeddings = 0
            failed_embeddings = 0

            for pdf_path in pdf_paths:
                # Get existing document
                existing_doc = self.registry.get_document_by_path(pdf_path)
                if existing_doc and existing_doc.status == DocumentStatus.EXTRACTED:
                    # Process for embedding only
                    result = embedding_pipeline.process_single_document(
                        pdf_path,
                        force_reprocess=force_reprocess
                    )
                    results.append(result)

                    if result["status"] == "success":
                        successful_embeddings += 1
                    else:
                        failed_embeddings += 1

            return {
                "documents_processed": len(pdf_paths),
                "successful_extractions": 0,  # No extraction was done
                "failed_extractions": 0,
                "successful_embeddings": successful_embeddings,
                "failed_embeddings": failed_embeddings,
                "results": results,
            }
        # Regular processing
        pdf_list = [str(path) for path in pdf_paths]
        results = self.ingestion_pipeline.process_batch(
            pdf_list=pdf_list,
            force_reprocess=force_reprocess
        )

        # Count results
        successful = len([r for r in results if r.get("status") == "success"])
        failed = len([r for r in results if r.get("status") == "error"])

        # For full processing, successful extractions = successful embeddings
        return {
            "documents_processed": len(pdf_paths),
            "successful_extractions": successful,
            "failed_extractions": failed,
            "successful_embeddings": successful,
            "failed_embeddings": failed,
            "results": results,
        }
