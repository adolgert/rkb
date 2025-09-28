"""Core components of the RKB system.

This module contains the fundamental interfaces, models, and registry components
that form the foundation of the Research Knowledge Base system.
"""

from rkb.core.document_registry import DocumentRegistry
from rkb.core.interfaces import ExtractorInterface, EmbedderInterface
from rkb.core.models import Document, ExtractionResult, EmbeddingResult

__all__ = [
    "DocumentRegistry",
    "ExtractorInterface",
    "EmbedderInterface",
    "Document",
    "ExtractionResult",
    "EmbeddingResult",
]