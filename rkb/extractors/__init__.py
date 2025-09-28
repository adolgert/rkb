"""Document extraction modules.

This package contains various document extraction implementations including
Nougat OCR for mathematical content, PyMuPDF for general text, and Pandoc
for LaTeX conversion.
"""

from rkb.extractors.base import get_extractor
from rkb.extractors.nougat_extractor import NougatExtractor

__all__ = [
    "NougatExtractor",
    "get_extractor",
]
