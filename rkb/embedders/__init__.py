"""Document embedding modules.

This package contains various embedding implementations for converting
extracted text into vector representations for semantic search.
"""

from rkb.embedders.base import get_embedder, list_embedders
from rkb.embedders.chroma_embedder import ChromaEmbedder
from rkb.embedders.ollama_embedder import OllamaEmbedder
from rkb.embedders.specter2_embedder import Specter2Embedder

__all__ = [
    "ChromaEmbedder",
    "OllamaEmbedder",
    "Specter2Embedder",
    "get_embedder",
    "list_embedders",
]
