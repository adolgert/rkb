"""Ingestion pipeline for processing documents through extraction and embedding."""

import hashlib
import json
import logging
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from rkb.core.checkpoint_manager import CheckpointManager
from rkb.core.document_registry import DocumentRegistry
from rkb.core.models import Document, DocumentStatus
from rkb.core.text_processing import chunk_text_by_pages, extract_equations
from rkb.embedders.base import get_embedder
from rkb.extractors.base import get_extractor

LOGGER = logging.getLogger("rkb.pipelines.ingestion_pipeline")


class IngestionPipeline:
    """Pipeline for ingesting documents through extraction and embedding."""

    def __init__(
        self,
        registry: DocumentRegistry | None = None,
        extractor_name: str = "nougat",
        embedder_name: str = "chroma",
        project_id: str | None = None,
        skip_embedding: bool = False,
        checkpoint_dir: Path | None = None,
        max_pages: int = 500,
    ):
        """Initialize ingestion pipeline.

        Args:
            registry: Document registry for tracking documents
            extractor_name: Name of extractor to use
            embedder_name: Name of embedder to use
            project_id: Project identifier for document organization
            skip_embedding: If True, only perform extraction, skip embedding
            checkpoint_dir: Directory for checkpoint files (default: .checkpoints)
            max_pages: Maximum pages per PDF to process
        """
        self.registry = registry or DocumentRegistry()
        self.extractor_name = extractor_name
        self.embedder_name = embedder_name
        self.project_id = project_id
        self.skip_embedding = skip_embedding

        # Initialize components
        self.extractor = get_extractor(extractor_name, max_pages=max_pages)
        self.embedder = get_embedder(embedder_name) if not skip_embedding else None

        # Interrupt handling
        self.interrupted = False
        self.checkpoint_manager = CheckpointManager(
            checkpoint_dir or Path(".checkpoints")
        )
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, _signum: int, _frame: Any) -> None:  # noqa: ANN401
        """Handle interrupt signal.

        Args:
            _signum: Signal number (unused, required by signal interface)
            _frame: Current stack frame (unused, required by signal interface)
        """
        LOGGER.warning("\n⚠️  Interrupt received. Saving checkpoint...")
        self.interrupted = True
        # Don't exit immediately - let pipeline save state

    def process_single_document(
        self,
        source_path: Path,
        force_reprocess: bool = False,
        max_chunk_size: int = 2000,
    ) -> dict[str, Any]:
        """Process a single document through extraction and embedding.

        Args:
            source_path: Path to the document to process
            force_reprocess: Whether to reprocess if already exists
            max_chunk_size: Maximum size for text chunks

        Returns:
            Dictionary with processing results
        """
        source_path = Path(source_path)

        if not source_path.exists():
            return {
                "status": "error",
                "message": f"File not found: {source_path}",
                "source_path": str(source_path),
            }

        start_time = time.time()

        try:
            # Check if document already exists using the new method
            document, is_new = self.registry.process_new_document(source_path, self.project_id)

            if document.status == DocumentStatus.INDEXED and not force_reprocess:
                return {
                    "status": "skipped",
                    "message": "Document already fully processed",
                    "source_path": str(source_path),
                    "doc_id": document.doc_id,
                }

            if not is_new and not force_reprocess:
                return {
                    "status": "duplicate",
                    "message": "Document already exists with content hash",
                    "source_path": str(source_path),
                    "doc_id": document.doc_id,
                    "content_hash": document.content_hash,
                }

            LOGGER.info(f"Processing: {source_path.name} (doc_id: {document.doc_id[:8]}...)")

            # Update document status
            self.registry.update_document_status(document.doc_id, DocumentStatus.EXTRACTING)

            # Extract content - pass doc_id for consistent naming
            LOGGER.debug(f"  Starting extraction with {self.extractor.name}...")
            extraction_result = self.extractor.extract(source_path, document.doc_id)
            LOGGER.debug(f"  Extraction completed with status: {extraction_result.status.value}")

            # Set document ID in extraction result
            extraction_result.doc_id = document.doc_id

            if extraction_result.status.value != "complete":
                # Update document status to failed
                self.registry.update_document_status(document.doc_id, DocumentStatus.FAILED)

                LOGGER.warning(f"  Extraction failed: {extraction_result.error_message}")

                return {
                    "status": "error",
                    "message": f"Extraction failed: {extraction_result.error_message}",
                    "source_path": str(source_path),
                    "doc_id": document.doc_id,
                    "processing_time": round(time.time() - start_time, 1),
                }

            # Add extraction to registry
            self.registry.add_extraction(extraction_result)

            # Process content if available
            if extraction_result.content:
                # Extract equations
                equation_info = extract_equations(extraction_result.content)

                # Chunk the text (returns tuples of (chunk_text, page_numbers))
                chunks_with_pages = chunk_text_by_pages(extraction_result.content, max_chunk_size)
                LOGGER.debug(f"  Created {len(chunks_with_pages)} chunks")

                if chunks_with_pages and not self.skip_embedding:
                    # Extract text and page numbers for embedding
                    valid_chunks_data = [
                        (chunk, pages) for chunk, pages in chunks_with_pages
                        if len(chunk.strip()) >= 50
                    ]

                    if valid_chunks_data:
                        # Prepare chunk texts and metadata
                        valid_chunks = [chunk for chunk, _ in valid_chunks_data]
                        chunk_metadatas = []

                        # Get PDF name from document object
                        pdf_name = (
                            getattr(document.source_path, "name", None)
                            if document.source_path
                            else None
                        )

                        for i, (chunk, pages) in enumerate(valid_chunks_data):
                            # Analyze equations in this chunk
                            chunk_eq_info = extract_equations(chunk)

                            # Create metadata dict for this chunk
                            metadata = {
                                "doc_id": document.doc_id,
                                "chunk_index": i,
                                "page_numbers": pages,
                                "has_equations": chunk_eq_info["has_equations"],
                                "display_eq_count": len(chunk_eq_info["display_equations"]),
                                "inline_eq_count": len(chunk_eq_info["inline_equations"]),
                            }

                            # Add optional fields if available
                            if pdf_name:
                                metadata["pdf_name"] = pdf_name
                            if document.project_id:
                                metadata["project_id"] = document.project_id

                            chunk_metadatas.append(metadata)

                        # Generate embeddings with metadata
                        embedding_result = self.embedder.embed(valid_chunks, chunk_metadatas)

                        # Set document and extraction references
                        embedding_result.doc_id = document.doc_id
                        embedding_result.extraction_id = extraction_result.extraction_id

                        # Add embedding to registry
                        self.registry.add_embedding(embedding_result)

                        if embedding_result.error_message:
                            LOGGER.warning(f"  Embedding errors: {embedding_result.error_message}")

            # Update document status based on whether embedding was skipped
            if self.skip_embedding:
                # Only extraction was performed
                self.registry.update_document_status(document.doc_id, DocumentStatus.EXTRACTED)
            else:
                # Full pipeline including embedding
                self.registry.update_document_status(document.doc_id, DocumentStatus.INDEXED)

            processing_time = time.time() - start_time
            LOGGER.info(f"  Completed in {processing_time:.1f}s")

            # Calculate chunk information
            chunk_count = len(chunks_with_pages) if extraction_result.content else 0
            valid_chunk_count = 0
            if extraction_result.content and chunks_with_pages and not self.skip_embedding:
                chunk_texts = [chunk for chunk, _ in chunks_with_pages]
                valid_chunks = [chunk for chunk in chunk_texts if len(chunk.strip()) >= 50]
                valid_chunk_count = len(valid_chunks)

            return {
                "status": "success",
                "source_path": str(source_path),
                "doc_id": document.doc_id,
                "extraction_id": extraction_result.extraction_id,
                "chunk_count": chunk_count,
                "valid_chunk_count": valid_chunk_count,
                "has_equations": equation_info["has_equations"]
                if extraction_result.content
                else False,
                "processing_time": round(processing_time, 1),
                "timestamp": datetime.now().isoformat(),
                "embedding_skipped": self.skip_embedding,
            }

        except Exception as e:
            # Update document status to failed if we have a document
            if "document" in locals():
                self.registry.update_document_status(document.doc_id, DocumentStatus.FAILED)

            processing_time = time.time() - start_time
            LOGGER.exception("  Error")

            return {
                "status": "error",
                "message": str(e),
                "source_path": str(source_path),
                "doc_id": getattr(document, "doc_id", None) if "document" in locals() else None,
                "processing_time": round(processing_time, 1),
            }

    def process_batch(
        self,
        pdf_list: list[str] | list[dict] | str,
        max_files: int | None = None,
        force_reprocess: bool = False,
        max_chunk_size: int = 2000,
        log_file: str | None = None,
        resume: bool = True,
    ) -> list[dict[str, Any]]:
        """Process a batch of documents with checkpoint/resume support.

        Args:
            pdf_list: List of file paths, list of dicts with 'path' key, or path to JSON file
            max_files: Maximum number of files to process
            force_reprocess: Whether to reprocess existing documents
            max_chunk_size: Maximum size for text chunks
            log_file: Optional path to save processing log
            resume: Whether to resume from checkpoint if available

        Returns:
            List of processing results
        """
        # Handle different input types
        if isinstance(pdf_list, str):
            # Load from JSON file
            pdf_list_path = Path(pdf_list)
            if not pdf_list_path.exists():
                raise FileNotFoundError(f"PDF list file not found: {pdf_list_path}")

            with pdf_list_path.open() as f:
                pdf_files = json.load(f)
        else:
            pdf_files = pdf_list

        # Normalize to list of paths
        if pdf_files and isinstance(pdf_files[0], dict):
            # Extract paths from dict format
            file_paths = [Path(item["path"]) for item in pdf_files]
        else:
            file_paths = [Path(p) for p in pdf_files]

        if max_files:
            file_paths = file_paths[:max_files]

        # Generate batch ID from paths hash
        batch_id = hashlib.md5(
            "".join(str(p) for p in file_paths).encode()
        ).hexdigest()[:16]

        # Check for existing checkpoint
        original_count = len(file_paths)
        if resume:
            file_paths = self.checkpoint_manager.get_remaining_files(
                batch_id, file_paths
            )
            if len(file_paths) < original_count:
                LOGGER.info(
                    f"📋 Resuming: {len(file_paths)}/{original_count} files remaining"
                )

        LOGGER.info(f"Processing {len(file_paths)} documents...")

        # Process each file
        results = []
        completed = []
        success_count = 0
        error_count = 0
        skip_count = 0
        start_time = time.time()

        for i, file_path in enumerate(file_paths, 1):
            # Check for interrupt before each file
            if self.interrupted:
                LOGGER.info(
                    f"\n💾 Saving checkpoint... ({i-1}/{len(file_paths)} completed)"
                )
                self.checkpoint_manager.save_checkpoint(
                    batch_id,
                    completed_files=[str(p) for p in completed],
                    metadata={"total": original_count},
                )
                LOGGER.info("✓ Checkpoint saved. Run again to resume.")
                sys.exit(0)

            LOGGER.info(f"[{i}/{len(file_paths)}] {file_path.name}")

            result = self.process_single_document(
                file_path,
                force_reprocess=force_reprocess,
                max_chunk_size=max_chunk_size,
            )
            results.append(result)
            completed.append(file_path)

            if result["status"] == "success":
                success_count += 1
            elif result["status"] in ("skipped", "duplicate"):
                skip_count += 1
            else:
                error_count += 1

            # Save progress log if requested
            if log_file:
                log_data = {
                    "timestamp": datetime.now().isoformat(),
                    "pipeline_config": {
                        "extractor": self.extractor_name,
                        "embedder": self.embedder_name,
                        "project_id": self.project_id,
                    },
                    "total_files": len(file_paths),
                    "processed": i,
                    "success": success_count,
                    "errors": error_count,
                    "skipped": skip_count,
                    "results": results,
                }

                log_path = Path(log_file)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with log_path.open("w") as f:
                    json.dump(log_data, f, indent=2)

        # Clear checkpoint on successful completion
        self.checkpoint_manager.clear_checkpoint(batch_id)

        total_time = time.time() - start_time

        # Print summary
        LOGGER.info("Processing Summary:")
        LOGGER.info(f"   Total files: {len(file_paths)}")
        LOGGER.info(f"   Successful: {success_count}")
        LOGGER.info(f"   Errors: {error_count}")
        LOGGER.info(f"   Skipped: {skip_count}")
        LOGGER.info(f"   Total time: {total_time / 60:.1f} minutes")
        if success_count > 0:
            LOGGER.info(f"   Avg time per file: {total_time / success_count:.1f}s")

        if log_file:
            LOGGER.info(f"Results saved to: {log_file}")

        return results

    def get_processing_stats(self) -> dict[str, Any]:
        """Get processing statistics from the registry.

        Returns:
            Dictionary with processing statistics
        """
        stats = self.registry.get_processing_stats()

        # Add pipeline-specific information
        stats.update(
            {
                "extractor": self.extractor_name,
                "embedder": self.embedder_name,
                "project_id": self.project_id,
            }
        )

        return stats

    def list_documents(self, status: DocumentStatus | None = None) -> list[Document]:
        """List documents in the registry.

        Args:
            status: Optional status filter

        Returns:
            List of documents
        """
        if status:
            return self.registry.get_documents_by_status(status)
        if self.project_id:
            return self.registry.get_documents_by_project(self.project_id)
        # Get all documents - would need a method for this
        return []

    def retry_failed_documents(self, max_chunk_size: int = 2000) -> list[dict[str, Any]]:
        """Retry processing of failed documents.

        Args:
            max_chunk_size: Maximum size for text chunks

        Returns:
            List of processing results
        """
        failed_docs = self.registry.get_documents_by_status(DocumentStatus.FAILED)

        if not failed_docs:
            LOGGER.info("No failed documents to retry")
            return []

        LOGGER.info(f"Retrying {len(failed_docs)} failed documents...")

        results = []
        for doc in failed_docs:
            if doc.source_path:
                result = self.process_single_document(
                    doc.source_path,
                    force_reprocess=True,
                    max_chunk_size=max_chunk_size,
                )
                results.append(result)

        return results
