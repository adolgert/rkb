"""Research Knowledge Base (RKB).

A personal research knowledge base system for semantic search, document management,
and experimental analysis of academic papers with equation-aware OCR capabilities.
"""

__version__ = "0.1.0"
__author__ = "Adam Dolgert"

# Public API exports
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