"""Tests for metadata_sources and metadata_resolved tables in Catalog."""

from rkb.collection.catalog import Catalog


def _make_catalog():
    catalog = Catalog(db_path=":memory:")  # type: ignore[arg-type]
    catalog.initialize()
    # Need a canonical_files row for foreign-key-like integrity
    catalog.add_canonical_file(
        content_sha256="a" * 64,
        canonical_path="/tmp/test.pdf",
        display_name="test.pdf",
        original_filename="test.pdf",
        page_count=5,
        file_size_bytes=1000,
    )
    return catalog


def test_add_and_get_metadata_source():
    catalog = _make_catalog()
    catalog.add_metadata_source(
        "a" * 64,
        "grobid",
        title="Paper Title",
        authors=["Alice", "Bob"],
        year=2023,
        journal="Nature",
        abstract="Some abstract text.",
    )

    sources = catalog.get_metadata_sources("a" * 64)
    assert len(sources) == 1
    assert sources[0]["title"] == "Paper Title"
    assert sources[0]["authors"] == ["Alice", "Bob"]
    assert sources[0]["year"] == 2023
    assert sources[0]["abstract"] == "Some abstract text."


def test_multiple_sources_same_hash():
    catalog = _make_catalog()
    catalog.add_metadata_source("a" * 64, "grobid", title="GROBID Title")
    catalog.add_metadata_source("a" * 64, "xmp", title="XMP Title")

    sources = catalog.get_metadata_sources("a" * 64)
    assert len(sources) == 2
    names = {s["extractor_name"] for s in sources}
    assert names == {"grobid", "xmp"}


def test_upsert_metadata_source():
    catalog = _make_catalog()
    catalog.add_metadata_source("a" * 64, "grobid", title="Old Title")
    catalog.add_metadata_source("a" * 64, "grobid", title="New Title")

    sources = catalog.get_metadata_sources("a" * 64)
    assert len(sources) == 1
    assert sources[0]["title"] == "New Title"


def test_set_and_get_resolved_metadata():
    catalog = _make_catalog()
    catalog.set_resolved_metadata(
        "a" * 64,
        title="Merged Title",
        authors=["Alice"],
        year=2023,
        abstract="Merged abstract.",
        resolution_method="rule_based",
        source_extractors=["grobid", "xmp"],
    )

    resolved = catalog.get_resolved_metadata("a" * 64)
    assert resolved is not None
    assert resolved["title"] == "Merged Title"
    assert resolved["authors"] == ["Alice"]
    assert resolved["source_extractors"] == ["grobid", "xmp"]
    assert resolved["resolution_method"] == "rule_based"


def test_get_resolved_metadata_missing():
    catalog = _make_catalog()
    assert catalog.get_resolved_metadata("b" * 64) is None


def test_get_unresolved_hashes():
    catalog = _make_catalog()
    unresolved = catalog.get_unresolved_hashes()
    assert "a" * 64 in unresolved

    catalog.set_resolved_metadata("a" * 64, title="Title")
    unresolved = catalog.get_unresolved_hashes()
    assert "a" * 64 not in unresolved


def test_upsert_resolved_metadata():
    catalog = _make_catalog()
    catalog.set_resolved_metadata("a" * 64, title="First")
    catalog.set_resolved_metadata("a" * 64, title="Updated")
    resolved = catalog.get_resolved_metadata("a" * 64)
    assert resolved["title"] == "Updated"
