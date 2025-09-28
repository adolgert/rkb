"""Processing pipelines for document ingestion and processing.

This package contains pipeline orchestration for document processing workflows
including ingestion, extraction, embedding, and indexing operations.
"""

from rkb.pipelines.ingestion_pipeline import IngestionPipeline
from rkb.pipelines.update_pipeline import UpdatePipeline

__all__ = [
    "IngestionPipeline",
    "UpdatePipeline",
]