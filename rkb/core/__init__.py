"""Core components of the RKB system.

This module contains the fundamental interfaces, models, and registry components
that form the foundation of the Research Knowledge Base system.
"""

from rkb.core.interfaces import EmbedderInterface, ExtractorInterface
from rkb.core.models import Document, EmbeddingResult, ExtractionResult

__all__ = [
    "Document",
    "EmbedderInterface",
    "EmbeddingResult",
    "ExtractionResult",
    "ExtractorInterface",
]
