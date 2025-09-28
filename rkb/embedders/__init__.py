"""Document embedding modules.

This package contains various embedding implementations for converting
extracted text into vector representations for semantic search.
"""

from rkb.embedders.base import get_embedder
from rkb.embedders.ollama_embedder import OllamaEmbedder
from rkb.embedders.openai_embedder import OpenAIEmbedder

__all__ = [
    "get_embedder",
    "OllamaEmbedder",
    "OpenAIEmbedder",
]