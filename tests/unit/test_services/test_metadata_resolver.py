"""Tests for MetadataResolver service."""

import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rkb.collection.catalog import Catalog
from rkb.extractors.metadata.models import DocumentMetadata
from rkb.extractors.metadata.xmp import XMPResult
from rkb.services.metadata_resolver import MetadataResolver, ResolutionResult


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
            patch.object(resolver._translation, "extract") as mock_translation,
            patch.object(resolver._grobid, "extract") as mock_grobid,
            patch.object(resolver._crossref, "extract") as mock_cr,
            patch.object(resolver._arxiv, "extract_by_id") as mock_arxiv,
            patch.object(resolver._s2, "extract_by_title") as mock_s2,
            patch.object(resolver._s2, "extract_by_doi") as mock_s2_doi,
        ):
            mock_xmp.return_value = XMPResult(
                metadata=_meta("xmp", title="Fresh"),
            )
            mock_translation.return_value = _meta("zotero_translation")
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
            patch.object(resolver._translation, "extract") as mock_translation,
            patch.object(resolver._grobid, "extract") as mock_grobid,
            patch.object(resolver._crossref, "extract") as mock_cr,
            patch.object(resolver._s2, "extract_by_title") as mock_s2,
        ):
            mock_xmp.return_value = XMPResult(
                metadata=_meta("xmp", title="XMP Only"),
            )
            mock_translation.return_value = _meta("zotero_translation")
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


class TestZoteroTranslation:
    def test_doi_from_xmp_reaches_translation_server(self, catalog):
        resolver = MetadataResolver(catalog, use_claude_merge=False)

        with (
            patch.object(resolver._xmp, "extract_with_ids") as mock_xmp,
            patch.object(resolver._translation, "extract_by_identifier") as mock_translation,
            patch.object(resolver._grobid, "extract") as mock_grobid,
            patch.object(resolver._crossref, "query_crossref") as mock_cr,
        ):
            mock_xmp.return_value = XMPResult(
                metadata=_meta("xmp", title="XMP Title"),
                doi="10.1000/xyz",
            )
            mock_translation.return_value = _meta(
                "zotero_translation",
                title="Authoritative Title",
                authors=["A. Author"],
                year=2024,
                abstract="From registrar.",
            )
            mock_grobid.return_value = _meta("grobid", title="Grobid Title")
            mock_cr.return_value = _meta("doi_crossref")

            result = resolver.resolve(Path("/tmp/test.pdf"), "a" * 64)

        mock_translation.assert_called_once_with("10.1000/xyz")
        # zotero_translation outranks grobid and xmp in the merge.
        assert result.title == "Authoritative Title"
        assert "zotero_translation" in result.source_extractors

    def test_full_translation_result_short_circuits_fallbacks(self, catalog):
        resolver = MetadataResolver(catalog, use_claude_merge=False)

        with (
            patch.object(resolver._xmp, "extract_with_ids") as mock_xmp,
            patch.object(resolver._translation, "extract_by_identifier") as mock_translation,
            patch.object(resolver._grobid, "extract") as mock_grobid,
            patch.object(resolver._crossref, "query_crossref") as mock_cr,
            patch.object(resolver._arxiv, "extract_by_id") as mock_arxiv,
            patch.object(resolver._s2, "extract_by_doi") as mock_s2,
        ):
            mock_xmp.return_value = XMPResult(metadata=_meta("xmp"), doi="10.1000/xyz")
            mock_translation.return_value = _meta(
                "zotero_translation",
                title="T",
                authors=["A"],
                year=2024,
                abstract="Abs",
            )
            mock_grobid.return_value = _meta("grobid")
            mock_cr.return_value = _meta("doi_crossref")

            resolver.resolve(Path("/tmp/test.pdf"), "a" * 64)

        mock_arxiv.assert_not_called()
        mock_s2.assert_not_called()


class TestTitleSearchFallback:
    def test_fallback_fires_when_no_source_has_title(self, catalog):
        resolver = MetadataResolver(catalog, use_claude_merge=False)

        with (
            patch.object(resolver._xmp, "extract_with_ids") as mock_xmp,
            patch.object(resolver._translation, "extract") as mock_translation,
            patch.object(resolver._grobid, "extract") as mock_grobid,
            patch.object(resolver._crossref, "extract") as mock_cr,
            patch.object(resolver._crossref, "search_by_title") as mock_cr_title,
            patch.object(resolver._s2, "extract_by_title") as mock_s2,
            patch.object(
                resolver,
                "_markdown_text",
                return_value="# A Scanned Paper\n\nXavier Author\n\nBody text.",
            ),
        ):
            mock_xmp.return_value = XMPResult(metadata=_meta("xmp"))
            mock_translation.return_value = _meta("zotero_translation")
            mock_grobid.return_value = _meta("grobid")
            mock_cr.return_value = _meta("doi_crossref")
            mock_cr_title.return_value = _meta(
                "crossref_title", title="A Scanned Paper", authors=["Xavier Author"], year=1990
            )
            mock_s2.return_value = _meta(
                "semantic_scholar_title", title="A Scanned Paper", authors=["Xavier Author"]
            )

            result = resolver.resolve(Path("/tmp/test.pdf"), "a" * 64)

        mock_cr_title.assert_called_once_with("A Scanned Paper")
        assert result.title == "A Scanned Paper"
        assert "crossref_title" in result.source_extractors
        assert "semantic_scholar_title" in result.source_extractors

    def test_fallback_skipped_when_a_source_has_title(self, catalog):
        resolver = MetadataResolver(catalog, use_claude_merge=False)

        with (
            patch.object(resolver._xmp, "extract_with_ids") as mock_xmp,
            patch.object(resolver._translation, "extract") as mock_translation,
            patch.object(resolver._grobid, "extract") as mock_grobid,
            patch.object(resolver._crossref, "extract") as mock_cr,
            patch.object(resolver._crossref, "search_by_title") as mock_cr_title,
            patch.object(resolver._s2, "extract_by_title") as mock_s2,
            patch.object(
                resolver, "_markdown_text", return_value="# Ignored\n\nBody."
            ),
        ):
            mock_xmp.return_value = XMPResult(metadata=_meta("xmp"))
            mock_translation.return_value = _meta("zotero_translation")
            mock_grobid.return_value = _meta("grobid", title="GROBID Title")
            mock_cr.return_value = _meta("doi_crossref")
            mock_s2.return_value = _meta("semantic_scholar")

            result = resolver.resolve(Path("/tmp/test.pdf"), "a" * 64)

        mock_cr_title.assert_not_called()
        assert result.title == "GROBID Title"

    def test_hit_without_author_on_title_page_is_rejected(self, catalog):
        resolver = MetadataResolver(catalog, use_claude_merge=False)

        with (
            patch.object(resolver._xmp, "extract_with_ids") as mock_xmp,
            patch.object(resolver._translation, "extract") as mock_translation,
            patch.object(resolver._grobid, "extract") as mock_grobid,
            patch.object(resolver._crossref, "extract") as mock_cr,
            patch.object(resolver._crossref, "search_by_title") as mock_cr_title,
            patch.object(resolver._s2, "extract_by_title") as mock_s2,
            patch.object(
                resolver,
                "_markdown_text",
                return_value="# Markov Chain Monte Carlo Methods\n\nNo author here.",
            ),
            # Mock the last-resort LLM stage so tests never hit a live API.
            patch.object(
                resolver._gemini_flash,
                "extract_from_text",
                return_value=_meta("gemini_flash"),
            ),
        ):
            mock_xmp.return_value = XMPResult(metadata=_meta("xmp"))
            mock_translation.return_value = _meta("zotero_translation")
            mock_grobid.return_value = _meta("grobid")
            mock_cr.return_value = _meta("doi_crossref")
            # Same generic title, but the claimed author never appears on the
            # title page — must be rejected as a probable different work.
            mock_cr_title.return_value = _meta(
                "crossref_title",
                title="Markov Chain Monte Carlo Methods",
                authors=["Christian P. Robert"],
            )
            mock_s2.return_value = _meta(
                "semantic_scholar_title",
                title="Markov Chain Monte Carlo Methods",
                authors=["Christian P. Robert"],
            )

            result = resolver.resolve(Path("/tmp/test.pdf"), "a" * 64)

        assert result.title is None
        assert "crossref_title" not in result.source_extractors

    def test_title_candidate_reads_markdown_from_canonical_layout(self, catalog, tmp_path):
        """Unmocked path lookup against a real canonical hash-dir layout."""
        sha = "a" * 64
        hash_dir = tmp_path / "library" / "sha256" / "aa" / "aa" / sha
        extraction_dir = hash_dir / "extractions" / "marker-pdf-1.10.2"
        extraction_dir.mkdir(parents=True)
        (extraction_dir / "extracted.md").write_text("# A Real Scanned Paper Title\n\nBody.")
        pdf_path = hash_dir / "Scanned.pdf"
        pdf_path.write_bytes(b"pdf")

        resolver = MetadataResolver(catalog, use_claude_merge=False)
        markdown = resolver._markdown_text(pdf_path)
        assert markdown is not None
        from rkb.core.text_processing import title_candidate_from_marker_markdown
        assert title_candidate_from_marker_markdown(markdown) == "A Real Scanned Paper Title"

    def test_missing_markdown_degrades_silently(self, catalog):
        resolver = MetadataResolver(catalog, use_claude_merge=False)

        with (
            patch.object(resolver._xmp, "extract_with_ids") as mock_xmp,
            patch.object(resolver._translation, "extract") as mock_translation,
            patch.object(resolver._grobid, "extract") as mock_grobid,
            patch.object(resolver._crossref, "extract") as mock_cr,
            patch.object(resolver._crossref, "search_by_title") as mock_cr_title,
        ):
            mock_xmp.return_value = XMPResult(metadata=_meta("xmp"))
            mock_translation.return_value = _meta("zotero_translation")
            mock_grobid.return_value = _meta("grobid")
            mock_cr.return_value = _meta("doi_crossref")

            result = resolver.resolve(Path("/tmp/test.pdf"), "a" * 64)

        mock_cr_title.assert_not_called()
        assert result.title is None


class TestGeminiFlashFallback:
    def _patch_registrars(self, stack, resolver):
        """Patch every registrar so only the fallback stages can produce a title."""
        stack.enter_context(patch.object(
            resolver._xmp, "extract_with_ids",
            return_value=XMPResult(metadata=_meta("xmp"))))
        stack.enter_context(patch.object(
            resolver._translation, "extract", return_value=_meta("zotero_translation")))
        stack.enter_context(patch.object(
            resolver._grobid, "extract", return_value=_meta("grobid")))
        stack.enter_context(patch.object(
            resolver._crossref, "extract", return_value=_meta("doi_crossref")))
        stack.enter_context(patch.object(
            resolver._s2, "extract_by_title", return_value=_meta("semantic_scholar")))

    def test_gemini_fires_only_when_title_search_found_nothing(self, catalog):
        resolver = MetadataResolver(catalog, use_claude_merge=False)
        markdown = "# Not A Title\n\nGloria Author\n\nBody text."

        with ExitStack() as stack:
            self._patch_registrars(stack, resolver)
            stack.enter_context(patch.object(
                resolver._crossref, "search_by_title", return_value=_meta("crossref_title")))
            stack.enter_context(patch.object(resolver, "_markdown_text", return_value=markdown))
            mock_gemini = stack.enter_context(
                patch.object(resolver._gemini_flash, "extract_from_text"))
            mock_gemini.return_value = _meta(
                "gemini_flash", title="Gloria's Real Paper", authors=["Gloria Author"], year=1985
            )
            result = resolver.resolve(Path("/tmp/test.pdf"), "a" * 64)

        mock_gemini.assert_called_once_with(markdown)
        assert result.title == "Gloria's Real Paper"
        assert "gemini_flash" in result.source_extractors

    def test_gemini_skipped_when_a_source_has_title(self, catalog):
        resolver = MetadataResolver(catalog, use_claude_merge=False)

        with (
            patch.object(resolver._xmp, "extract_with_ids",
                         return_value=XMPResult(metadata=_meta("xmp"))),
            patch.object(resolver._translation, "extract",
                         return_value=_meta("zotero_translation")),
            patch.object(resolver._grobid, "extract",
                         return_value=_meta("grobid", title="GROBID Title")),
            patch.object(resolver._crossref, "extract", return_value=_meta("doi_crossref")),
            patch.object(resolver._s2, "extract_by_title",
                         return_value=_meta("semantic_scholar")),
            patch.object(resolver._gemini_flash, "extract_from_text") as mock_gemini,
        ):
            result = resolver.resolve(Path("/tmp/test.pdf"), "a" * 64)

        mock_gemini.assert_not_called()
        assert result.title == "GROBID Title"

    def test_gemini_skipped_when_no_markdown(self, catalog):
        resolver = MetadataResolver(catalog, use_claude_merge=False)

        with ExitStack() as stack:
            self._patch_registrars(stack, resolver)
            stack.enter_context(patch.object(resolver, "_markdown_text", return_value=None))
            mock_gemini = stack.enter_context(
                patch.object(resolver._gemini_flash, "extract_from_text"))
            resolver.resolve(Path("/tmp/test.pdf"), "a" * 64)

        mock_gemini.assert_not_called()

    def test_gemini_title_feeds_title_search_and_upgrades(self, catalog):
        resolver = MetadataResolver(catalog, use_claude_merge=False)
        # Heading is generic, so the heading-based search yields nothing;
        # Gemini transcribes the real title, which corroborates via CrossRef.
        markdown = "# Introduction\n\nHilbert Author\n\nBody about spaces."

        with ExitStack() as stack:
            self._patch_registrars(stack, resolver)
            mock_cr_title = stack.enter_context(
                patch.object(resolver._crossref, "search_by_title"))
            # _patch_registrars stubs S2 extract_by_title to return a
            # title-less result, so only the crossref registrar match upgrades.
            stack.enter_context(patch.object(resolver, "_markdown_text", return_value=markdown))
            mock_gemini = stack.enter_context(
                patch.object(resolver._gemini_flash, "extract_from_text"))
            mock_gemini.return_value = _meta(
                "gemini_flash", title="On Hilbert Spaces", authors=["Hilbert Author"]
            )
            mock_cr_title.return_value = _meta(
                "crossref_title",
                title="On Hilbert Spaces",
                authors=["Hilbert Author"],
                year=1912,
            )
            result = resolver.resolve(Path("/tmp/test.pdf"), "a" * 64)

        mock_cr_title.assert_called_once_with("On Hilbert Spaces")
        assert "crossref_title" in result.source_extractors
        assert result.year == 1912


class TestFoundProperty:
    def test_found_true_when_metadata_present(self):
        result = ResolutionResult(content_sha256="a" * 64, title="A Title")
        assert result.found is True

    def test_found_true_from_authors_only(self):
        result = ResolutionResult(content_sha256="a" * 64, authors=["A. Author"])
        assert result.found is True

    def test_found_false_when_empty(self):
        result = ResolutionResult(content_sha256="a" * 64)
        assert result.found is False

    def test_found_true_for_cached_result(self):
        result = ResolutionResult(content_sha256="a" * 64, year=1999, cached=True)
        assert result.found is True


class TestResolveBatch:
    def test_batch_resolve(self, catalog, resolver):
        catalog.set_resolved_metadata("a" * 64, title="Batch Title")
        results = resolver.resolve_batch([(Path("/tmp/test.pdf"), "a" * 64)])
        assert len(results) == 1
        assert results[0].title == "Batch Title"
