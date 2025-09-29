"""Ingestion pipeline for processing documents through extraction and embedding."""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from rkb.core.document_registry import DocumentRegistry
from rkb.core.models import Document, DocumentStatus
from rkb.core.text_processing import chunk_text_by_pages, extract_equations
from rkb.embedders.base import get_embedder
from rkb.extractors.base import get_extractor

LOGGER = logging.getLogger('rkb.pipelines.ingestion_pipeline')


class IngestionPipeline:
    """Pipeline for ingesting documents through extraction and embedding."""

    def __init__(
        self,
        registry: DocumentRegistry | None = None,
        extractor_name: str = "nougat",
        embedder_name: str = "chroma",
        project_id: str | None = None,
        skip_embedding: bool = False,
    ):
        """Initialize ingestion pipeline.

        Args:
            registry: Document registry for tracking documents
            extractor_name: Name of extractor to use
            embedder_name: Name of embedder to use
            project_id: Project identifier for document organization
            skip_embedding: If True, only perform extraction, skip embedding
        """
        self.registry = registry or DocumentRegistry()
        self.extractor_name = extractor_name
        self.embedder_name = embedder_name
        self.project_id = project_id
        self.skip_embedding = skip_embedding

        # Initialize components
        self.extractor = get_extractor(extractor_name)
        self.embedder = get_embedder(embedder_name) if not skip_embedding else None

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
            extraction_result = self.extractor.extract(source_path, document.doc_id)

            # Set document ID in extraction result
            extraction_result.doc_id = document.doc_id

            if extraction_result.status.value != "complete":
                # Update document status to failed
                self.registry.update_document_status(document.doc_id, DocumentStatus.FAILED)

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

                # Chunk the text
                chunks = chunk_text_by_pages(extraction_result.content, max_chunk_size)
                LOGGER.debug(f"  Created {len(chunks)} chunks")

                if chunks and not self.skip_embedding:
                    # Generate embeddings only if not skipping
                    valid_chunks = [chunk for chunk in chunks if len(chunk.strip()) >= 50]

                    if valid_chunks:
                        embedding_result = self.embedder.embed(valid_chunks)

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
            chunk_count = len(chunks) if extraction_result.content else 0
            valid_chunk_count = 0
            if extraction_result.content and chunks and not self.skip_embedding:
                valid_chunks = [chunk for chunk in chunks if len(chunk.strip()) >= 50]
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
            LOGGER.error(f"  Error: {e}")

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
    ) -> list[dict[str, Any]]:
        """Process a batch of documents.

        Args:
            pdf_list: List of file paths, list of dicts with 'path' key, or path to JSON file
            max_files: Maximum number of files to process
            force_reprocess: Whether to reprocess existing documents
            max_chunk_size: Maximum size for text chunks
            log_file: Optional path to save processing log

        Returns:
            List of processing results
        """
        # Handle different input types
        if isinstance(pdf_list, str):
            # Load from JSON file
            pdf_list_path = Path(pdf_list)
            if not pdf_list_path.exists():
                raise FileNotFoundError(f"PDF list file not found: {pdf_list_path}")

            with open(pdf_list_path) as f:
                pdf_files = json.load(f)
        else:
            pdf_files = pdf_list

        # Normalize to list of paths
        if pdf_files and isinstance(pdf_files[0], dict):
            # Extract paths from dict format
            file_paths = [item["path"] for item in pdf_files]
        else:
            file_paths = pdf_files

        if max_files:
            file_paths = file_paths[:max_files]

        LOGGER.info(f"Processing {len(file_paths)} documents...")

        # Process each file
        results = []
        success_count = 0
        error_count = 0
        skip_count = 0
        start_time = time.time()

        for i, file_path in enumerate(file_paths, 1):
            LOGGER.info(f"[{i}/{len(file_paths)}] {Path(file_path).name}")

            result = self.process_single_document(
                Path(file_path),
                force_reprocess=force_reprocess,
                max_chunk_size=max_chunk_size,
            )
            results.append(result)

            if result["status"] == "success":
                success_count += 1
            elif result["status"] == "skipped":
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
                with open(log_path, "w") as f:
                    json.dump(log_data, f, indent=2)

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
