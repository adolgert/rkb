"""Ingestion pipeline for processing documents through extraction and embedding."""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from rkb.core.document_registry import DocumentRegistry
from rkb.core.models import Document, DocumentStatus
from rkb.core.text_processing import chunk_text_by_pages, extract_equations
from rkb.embedders.base import get_embedder
from rkb.extractors.base import get_extractor


class IngestionPipeline:
    """Pipeline for ingesting documents through extraction and embedding."""

    def __init__(
        self,
        registry: DocumentRegistry | None = None,
        extractor_name: str = "nougat",
        embedder_name: str = "chroma",
        project_id: str | None = None,
    ):
        """Initialize ingestion pipeline.

        Args:
            registry: Document registry for tracking documents
            extractor_name: Name of extractor to use
            embedder_name: Name of embedder to use
            project_id: Project identifier for document organization
        """
        self.registry = registry or DocumentRegistry()
        self.extractor_name = extractor_name
        self.embedder_name = embedder_name
        self.project_id = project_id

        # Initialize components
        self.extractor = get_extractor(extractor_name)
        self.embedder = get_embedder(embedder_name)

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

        # Check if document already exists
        if not force_reprocess and self.registry.document_exists(source_path):
            return {
                "status": "skipped",
                "message": "Document already processed",
                "source_path": str(source_path),
            }

        start_time = time.time()

        try:
            # Create document record
            document = Document(
                source_path=source_path,
                status=DocumentStatus.EXTRACTING,
            )
            # Set project_id as attribute (used by registry)
            if self.project_id:
                document.project_id = self.project_id

            # Add to registry
            if not self.registry.add_document(document):
                # Document already exists, get it
                existing_doc = self.registry.get_document_by_path(source_path)
                if existing_doc and not force_reprocess:
                    return {
                        "status": "skipped",
                        "message": "Document already in registry",
                        "source_path": str(source_path),
                        "doc_id": existing_doc.doc_id,
                    }
                document = existing_doc

            print(f"🔄 Processing: {source_path.name}")

            # Extract content
            extraction_result = self.extractor.extract(source_path)

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
                print(f"  📝 Created {len(chunks)} chunks")

                if chunks:
                    # Generate embeddings
                    valid_chunks = [chunk for chunk in chunks if len(chunk.strip()) >= 50]

                    if valid_chunks:
                        embedding_result = self.embedder.embed(valid_chunks)

                        # Set document and extraction references
                        embedding_result.doc_id = document.doc_id
                        embedding_result.extraction_id = extraction_result.extraction_id

                        # Add embedding to registry
                        self.registry.add_embedding(embedding_result)

                        if embedding_result.error_message:
                            print(f"  ⚠ Embedding errors: {embedding_result.error_message}")

            # Update document status to indexed (complete)
            self.registry.update_document_status(document.doc_id, DocumentStatus.INDEXED)

            processing_time = time.time() - start_time
            print(f"  ✓ Completed in {processing_time:.1f}s")

            return {
                "status": "success",
                "source_path": str(source_path),
                "doc_id": document.doc_id,
                "extraction_id": extraction_result.extraction_id,
                "chunk_count": len(chunks) if extraction_result.content else 0,
                "valid_chunk_count": len(valid_chunks) if extraction_result.content else 0,
                "has_equations": equation_info["has_equations"] if extraction_result.content else False,
                "processing_time": round(processing_time, 1),
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            # Update document status to failed if we have a document
            if "document" in locals():
                self.registry.update_document_status(document.doc_id, DocumentStatus.FAILED)

            processing_time = time.time() - start_time
            print(f"  ✗ Error: {e}")

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

        print(f"📄 Processing {len(file_paths)} documents...")

        # Process each file
        results = []
        success_count = 0
        error_count = 0
        skip_count = 0
        start_time = time.time()

        for i, file_path in enumerate(file_paths, 1):
            print(f"\n[{i}/{len(file_paths)}] {Path(file_path).name}")

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
        print("\n📊 Processing Summary:")
        print(f"   Total files: {len(file_paths)}")
        print(f"   Successful: {success_count}")
        print(f"   Errors: {error_count}")
        print(f"   Skipped: {skip_count}")
        print(f"   Total time: {total_time/60:.1f} minutes")
        if success_count > 0:
            print(f"   Avg time per file: {total_time/success_count:.1f}s")

        if log_file:
            print(f"\n💾 Results saved to: {log_file}")

        return results

    def get_processing_stats(self) -> dict[str, Any]:
        """Get processing statistics from the registry.

        Returns:
            Dictionary with processing statistics
        """
        stats = self.registry.get_processing_stats()

        # Add pipeline-specific information
        stats.update({
            "extractor": self.extractor_name,
            "embedder": self.embedder_name,
            "project_id": self.project_id,
        })

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
            print("No failed documents to retry")
            return []

        print(f"🔄 Retrying {len(failed_docs)} failed documents...")

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
