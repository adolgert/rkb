"""Tests for extractor base functionality."""

from pathlib import Path

import pytest

from rkb.core.interfaces import ExtractorInterface
from rkb.core.models import ExtractionResult, ExtractionStatus
from rkb.extractors.base import get_extractor, list_extractors, register_extractor


class MockExtractor(ExtractorInterface):
    """Mock extractor for testing."""

    @property
    def name(self) -> str:
        """Return the extractor name."""
        return "mock"

    @property
    def version(self) -> str:
        """Return the extractor version."""
        return "1.0.0"

    def extract(self, source_path: Path) -> ExtractionResult:
        """Mock extract method."""
        return ExtractionResult(
            doc_id=str(source_path),
            status=ExtractionStatus.COMPLETE,
        )

    def get_capabilities(self) -> dict:
        """Mock capabilities."""
        return {"name": "mock", "supported_formats": [".txt"]}


class TestExtractorBase:
    """Tests for extractor base functionality."""

    def test_register_and_get_extractor(self):
        """Test registering and retrieving an extractor."""
        # Register mock extractor
        register_extractor("mock", MockExtractor)

        # Check it's listed
        extractors = list_extractors()
        assert "mock" in extractors

        # Get the extractor
        extractor = get_extractor("mock")
        assert isinstance(extractor, MockExtractor)

    def test_get_unknown_extractor_raises_error(self):
        """Test that getting unknown extractor raises ValueError."""
        with pytest.raises(ValueError, match="Unknown extractor 'nonexistent'"):
            get_extractor("nonexistent")

    def test_nougat_extractor_is_registered(self):
        """Test that NougatExtractor is automatically registered."""
        extractors = list_extractors()
        assert "nougat" in extractors

        # Get the nougat extractor
        extractor = get_extractor("nougat")
        assert extractor is not None

        # Check capabilities
        capabilities = extractor.get_capabilities()
        assert capabilities["name"] == "nougat"
        assert ".pdf" in capabilities["supported_formats"]
