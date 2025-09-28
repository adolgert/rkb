"""Processing pipelines for document ingestion and processing.

This package contains pipeline orchestration for document processing workflows
including ingestion, extraction, embedding, and indexing operations.
"""

from rkb.pipelines.complete_pipeline import CompletePipeline
from rkb.pipelines.ingestion_pipeline import IngestionPipeline

__all__ = [
    "CompletePipeline",
    "IngestionPipeline",
]
