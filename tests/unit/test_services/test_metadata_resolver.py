"""Tests for MetadataResolver service."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rkb.collection.catalog import Catalog
from rkb.extractors.metadata.models import DocumentMetadata
from rkb.extractors.metadata.xmp import XMPResult
from rkb.services.metadata_resolver import MetadataResolver


@pytest.fixture
def catalog():
    cat = Catalog(db_path=":memory:")  # type: ignore[arg-type]
    cat.initialize()
    cat.add_canonical_file(
        content_sha256="a" * 64,
        canonical_path="/tmp/test.pdf",
        display_name="test.pdf",
        original_filename="test.pdf",
        page_count=5,
        file_size_bytes=1000,
    )
    return cat


@pytest.fixture
def resolver(catalog):
    return MetadataResolver(catalog, use_claude_merge=False)


def _meta(extractor, **kwargs):
    return DocumentMetadata(extractor=extractor, **kwargs)


class TestCacheHit:
    def test_returns_cached_result(self, catalog, resolver):
        catalog.set_resolved_metadata(
            "a" * 64,
            title="Cached Title",
            authors=["A"],
            year=2023,
            resolution_method="rule_based",
            source_extractors=["grobid"],
        )
        result = resolver.resolve(Path("/tmp/test.pdf"), "a" * 64)
        assert result.cached is True
        assert result.title == "Cached Title"

    def test_force_bypasses_cache(self, catalog, resolver):
        catalog.set_resolved_metadata("a" * 64, title="Old")

        with (
            patch.object(resolver._xmp, "extract_with_ids") as mock_xmp,
            patch.object(resolver._grobid, "extract") as mock_grobid,
            patch.object(resolver._crossref, "extract") as mock_cr,
            patch.object(resolver._arxiv, "extract_by_id") as mock_arxiv,
            patch.object(resolver._s2, "extract_by_title") as mock_s2,
            patch.object(resolver._s2, "extract_by_doi") as mock_s2_doi,
        ):
            mock_xmp.return_value = XMPResult(
                metadata=_meta("xmp", title="Fresh"),
            )
            mock_grobid.return_value = _meta("grobid")
            mock_cr.return_value = _meta("doi_crossref")
            mock_arxiv.return_value = _meta("arxiv")
            mock_s2.return_value = _meta("semantic_scholar")
            mock_s2_doi.return_value = _meta("semantic_scholar")

            result = resolver.resolve(Path("/tmp/test.pdf"), "a" * 64, force=True)
            assert result.cached is False
            assert result.title == "Fresh"


class TestRuleBasedMerge:
    def test_priority_order(self, resolver):
        sources = {
            "xmp": _meta("xmp", title="XMP Title", year=2020),
            "grobid": _meta("grobid", title="GROBID Title", year=2023),
        }
        result = resolver._rule_based_merge("a" * 64, sources)
        assert result.title == "GROBID Title"
        assert result.year == 2023

    def test_fills_from_lower_priority(self, resolver):
        sources = {
            "grobid": _meta("grobid", title="Title"),
            "arxiv": _meta("arxiv", abstract="Abstract from arXiv"),
        }
        result = resolver._rule_based_merge("a" * 64, sources)
        assert result.title == "Title"
        assert result.abstract == "Abstract from arXiv"

    def test_prefers_longest_author_list(self, resolver):
        sources = {
            "grobid": _meta("grobid", authors=["Smith"]),
            "semantic_scholar": _meta("semantic_scholar", authors=["A. Smith", "B. Jones"]),
        }
        result = resolver._rule_based_merge("a" * 64, sources)
        assert result.authors == ["A. Smith", "B. Jones"]


class TestClaudeMerge:
    def test_claude_merge_success(self, catalog):
        resolver = MetadataResolver(
            catalog, anthropic_api_key="test-key", use_claude_merge=True
        )
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text='{"title": "Merged", "authors": ["A"], '
                                          '"year": 2023, "abstract": "Abs", '
                                          '"journal": "J", "doc_type": "article"}')]

        mock_anthropic = MagicMock()
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_message
        mock_anthropic.Anthropic.return_value = mock_client

        original = sys.modules.get("anthropic")
        sys.modules["anthropic"] = mock_anthropic
        try:
            sources = {
                "grobid": _meta("grobid", title="G Title"),
                "xmp": _meta("xmp", title="X Title"),
            }
            result = resolver._claude_merge("a" * 64, sources)
            assert result.title == "Merged"
            assert result.resolution_method == "claude_merge"
        finally:
            if original is None:
                sys.modules.pop("anthropic", None)
            else:
                sys.modules["anthropic"] = original

    def test_claude_merge_fallback_on_error(self, catalog):
        resolver = MetadataResolver(
            catalog, anthropic_api_key="test-key", use_claude_merge=True
        )

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.side_effect = Exception("API error")

        original = sys.modules.get("anthropic")
        sys.modules["anthropic"] = mock_anthropic
        try:
            sources = {
                "grobid": _meta("grobid", title="Fallback Title"),
            }
            result = resolver._claude_merge("a" * 64, sources)
            assert result.title == "Fallback Title"
            assert result.resolution_method == "rule_based"
        finally:
            if original is None:
                sys.modules.pop("anthropic", None)
            else:
                sys.modules["anthropic"] = original


class TestAllFieldsFilled:
    def test_all_filled(self):
        sources = {
            "grobid": _meta("grobid", title="T", authors=["A"], year=2023, abstract="Abs"),
        }
        assert MetadataResolver._all_fields_filled(sources) is True

    def test_missing_abstract(self):
        sources = {
            "grobid": _meta("grobid", title="T", authors=["A"], year=2023),
        }
        assert MetadataResolver._all_fields_filled(sources) is False


class TestGrobidUnavailable:
    def test_works_without_grobid(self, catalog):
        resolver = MetadataResolver(catalog, use_claude_merge=False)

        with (
            patch.object(resolver._xmp, "extract_with_ids") as mock_xmp,
            patch.object(resolver._grobid, "extract") as mock_grobid,
            patch.object(resolver._crossref, "extract") as mock_cr,
            patch.object(resolver._s2, "extract_by_title") as mock_s2,
        ):
            mock_xmp.return_value = XMPResult(
                metadata=_meta("xmp", title="XMP Only"),
            )
            mock_grobid.side_effect = Exception("GROBID down")
            mock_cr.return_value = _meta("doi_crossref")
            mock_s2.return_value = _meta(
                "semantic_scholar",
                title="S2 Title",
                authors=["Author"],
                year=2023,
                abstract="S2 abstract",
            )

            result = resolver.resolve(Path("/tmp/test.pdf"), "a" * 64)
            assert result.title in ("XMP Only", "S2 Title")
            assert result.resolution_method == "rule_based"


class TestResolveBatch:
    def test_batch_resolve(self, catalog, resolver):
        catalog.set_resolved_metadata("a" * 64, title="Batch Title")
        results = resolver.resolve_batch([(Path("/tmp/test.pdf"), "a" * 64)])
        assert len(results) == 1
        assert results[0].title == "Batch Title"
