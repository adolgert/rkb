"""Tests for rkb.collection.bibtex — citation key generation and BibTeX formatting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from rkb.collection.bibtex import (
    format_bib_entry,
    generate_citation_key,
    write_bib_file,
)

SHA = "0006d958c6c7aabbccdd1122"


@dataclass
class FakeResult:
    """Minimal stand-in for ResolutionResult."""

    title: str | None = None
    authors: list[str] | None = None
    year: int | None = None
    abstract: str | None = None
    journal: str | None = None
    doc_type: str | None = None
    content_sha256: str = SHA
    resolution_method: str = "rule_based"
    source_extractors: list[str] = field(default_factory=list)
    cached: bool = False


class TestGenerateCitationKey:
    def test_citation_key_full(self):
        result = FakeResult(
            title="Deep Learning Methods",
            authors=["Smith, John", "Doe, Jane"],
            year=2023,
        )
        key = generate_citation_key(result, SHA)
        assert key == "smith-2023-deep-0006d958c6c7"

    def test_citation_key_missing_author(self):
        result = FakeResult(title="Deep Learning Methods", year=2023)
        key = generate_citation_key(result, SHA)
        assert key == "unknown-2023-deep-0006d958c6c7"

    def test_citation_key_missing_year(self):
        result = FakeResult(
            title="Deep Learning Methods",
            authors=["Smith, John"],
        )
        key = generate_citation_key(result, SHA)
        assert key == "smith-nodate-deep-0006d958c6c7"

    def test_citation_key_skips_articles(self):
        result = FakeResult(
            title="The Deep Method",
            authors=["Smith, John"],
            year=2023,
        )
        key = generate_citation_key(result, SHA)
        assert key == "smith-2023-deep-0006d958c6c7"

    def test_citation_key_unicode_author(self):
        result = FakeResult(
            title="Neural Networks",
            authors=["Müller, Hans"],
            year=2021,
        )
        key = generate_citation_key(result, SHA)
        assert key == "muller-2021-neural-0006d958c6c7"

    def test_citation_key_first_last_format(self):
        """Author given as 'First Last' rather than 'Last, First'."""
        result = FakeResult(
            title="Neural Networks",
            authors=["Hans Müller"],
            year=2021,
        )
        key = generate_citation_key(result, SHA)
        assert key == "muller-2021-neural-0006d958c6c7"


class TestFormatBibEntry:
    def test_format_bib_article(self):
        result = FakeResult(
            title="Deep Learning",
            authors=["Smith, John", "Doe, Jane"],
            year=2023,
            journal="Nature",
            doc_type="journal-article",
        )
        bib = format_bib_entry(result, "smith-2023-deep-abc123")
        assert bib.startswith("@article{smith-2023-deep-abc123,")
        assert "author = {Smith, John and Doe, Jane}," in bib
        assert "journal = {Nature}," in bib
        assert "title = {Deep Learning}," in bib
        assert "year = {2023}," in bib

    def test_format_bib_inproceedings(self):
        result = FakeResult(
            title="A Method",
            authors=["Lee, Alice"],
            year=2022,
            journal="ICML 2022",
            doc_type="proceedings-article",
        )
        bib = format_bib_entry(result, "lee-2022-method-abc")
        assert bib.startswith("@inproceedings{lee-2022-method-abc,")
        assert "booktitle = {ICML 2022}," in bib
        assert "journal" not in bib.lower().split("booktitle")[0]

    def test_format_bib_omits_none_fields(self):
        result = FakeResult(title="Solo Title", doc_type="journal-article")
        bib = format_bib_entry(result, "key")
        assert "author" not in bib
        assert "year" not in bib
        assert "abstract" not in bib
        assert "title = {Solo Title}," in bib

    def test_format_bib_default_misc(self):
        result = FakeResult(title="Something", doc_type="unknown-type")
        bib = format_bib_entry(result, "key")
        assert bib.startswith("@misc{key,")

    def test_format_bib_fields_sorted(self):
        result = FakeResult(
            title="Title",
            authors=["A, B"],
            year=2020,
            abstract="An abstract.",
            journal="J",
            doc_type="journal-article",
        )
        bib = format_bib_entry(result, "k")
        lines = [line.strip() for line in bib.splitlines() if "=" in line]
        keys = [line.split("=")[0].strip() for line in lines]
        assert keys == sorted(keys)


class TestWriteBibFile:
    def test_write_bib_file(self, tmp_path: Path):
        result = FakeResult(
            title="Deep Learning",
            authors=["Smith, John"],
            year=2023,
            doc_type="journal-article",
        )
        bib_path = write_bib_file(tmp_path, result, SHA)
        assert bib_path == tmp_path / "metadata.bib"
        assert bib_path.exists()
        content = bib_path.read_text(encoding="utf-8")
        assert "@article{smith-2023-deep-0006d958c6c7," in content
        assert "title = {Deep Learning}," in content
