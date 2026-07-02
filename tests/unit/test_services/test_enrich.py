"""Tests for the enrich service."""

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

from rkb.collection.catalog import Catalog
from rkb.services.enrich import EnrichSummary, enrich_collection


@dataclass
class _FakeConfig:
    library_root: Path
    catalog_db: Path
    machine_id: str = "test"


def _setup_catalog_and_pdf(tmp_path, content_sha256):
    """Set up a catalog with one canonical file and a real PDF on disk."""
    db_path = tmp_path / "db" / "catalog.db"
    db_path.parent.mkdir(parents=True)
    library_root = tmp_path / "library"

    # Create canonical dir with a PDF
    prefix1, prefix2 = content_sha256[:2], content_sha256[2:4]
    hash_dir = library_root / "sha256" / prefix1 / prefix2 / content_sha256
    hash_dir.mkdir(parents=True)
    pdf_path = hash_dir / "original.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test")

    catalog = Catalog(db_path)
    catalog.initialize()
    catalog.add_canonical_file(
        content_sha256=content_sha256,
        canonical_path=str(pdf_path),
        display_name="original.pdf",
        original_filename="original.pdf",
        page_count=1,
        file_size_bytes=13,
    )
    catalog.close()

    return _FakeConfig(library_root=library_root, catalog_db=db_path)


_HASH = "b" * 64


class TestEnrichCollection:
    def test_resolve_and_rename(self, tmp_path):
        config = _setup_catalog_and_pdf(tmp_path, _HASH)

        resolver = MagicMock()
        resolver.resolve.return_value = MagicMock(
            cached=False,
            title="Deep Learning Foundations",
            authors=["Smith, John", "Doe, Jane"],
            year=2023,
        )

        summary = enrich_collection(config, resolver, hashes=[_HASH])

        assert summary.total == 1
        assert summary.resolved == 1
        assert summary.renamed == 1
        assert summary.failed == 0

        # Verify the rename happened on disk
        catalog = Catalog(config.catalog_db)
        catalog.initialize()
        row = catalog.get_canonical_file(_HASH)
        catalog.close()
        assert "Deep Learning Foundations" in row["display_name"]

    def test_already_resolved_skip(self, tmp_path):
        config = _setup_catalog_and_pdf(tmp_path, _HASH)

        # Pre-populate resolved metadata
        catalog = Catalog(config.catalog_db)
        catalog.initialize()
        catalog.set_resolved_metadata(
            _HASH, title="Existing", resolution_method="rule_based",
        )
        catalog.close()

        resolver = MagicMock()
        resolver.resolve.return_value = MagicMock(cached=True)

        summary = enrich_collection(config, resolver, hashes=[_HASH])

        assert summary.already_resolved == 1
        assert summary.resolved == 0

    def test_force_re_resolves(self, tmp_path):
        config = _setup_catalog_and_pdf(tmp_path, _HASH)

        # Pre-populate resolved metadata
        catalog = Catalog(config.catalog_db)
        catalog.initialize()
        catalog.set_resolved_metadata(
            _HASH, title="Old Title", resolution_method="rule_based",
        )
        catalog.close()

        resolver = MagicMock()
        resolver.resolve.return_value = MagicMock(
            cached=False,
            title="New Title",
            authors=["Author"],
            year=2024,
        )

        summary = enrich_collection(config, resolver, hashes=[_HASH], force=True)

        assert summary.resolved == 1
        assert summary.renamed == 1

    def test_dry_run_no_modification(self, tmp_path):
        config = _setup_catalog_and_pdf(tmp_path, _HASH)

        resolver = MagicMock()

        summary = enrich_collection(config, resolver, hashes=[_HASH], dry_run=True)

        assert summary.resolved == 1
        assert summary.renamed == 0
        resolver.resolve.assert_not_called()

        # Verify nothing changed on disk
        catalog = Catalog(config.catalog_db)
        catalog.initialize()
        row = catalog.get_canonical_file(_HASH)
        catalog.close()
        assert row["display_name"] == "original.pdf"

    def test_no_rename_when_disabled(self, tmp_path):
        config = _setup_catalog_and_pdf(tmp_path, _HASH)

        resolver = MagicMock()
        resolver.resolve.return_value = MagicMock(
            cached=False,
            title="Some Title",
            authors=["Author"],
            year=2023,
        )

        summary = enrich_collection(config, resolver, hashes=[_HASH], rename=False)

        assert summary.resolved == 1
        assert summary.renamed == 0

    def test_resolver_failure_counted(self, tmp_path):
        config = _setup_catalog_and_pdf(tmp_path, _HASH)

        resolver = MagicMock()
        resolver.resolve.side_effect = RuntimeError("network error")

        summary = enrich_collection(config, resolver, hashes=[_HASH])

        assert summary.failed == 1
        assert len(summary.failures) == 1
        assert "network error" in summary.failures[0].error

    def test_nothing_found_counted_separately(self, tmp_path):
        config = _setup_catalog_and_pdf(tmp_path, _HASH)

        resolver = MagicMock()
        resolver.resolve.return_value = MagicMock(
            cached=False,
            found=False,
            title=None,
            authors=None,
            year=None,
        )

        summary = enrich_collection(config, resolver, hashes=[_HASH])

        assert summary.resolved == 0
        assert summary.nothing_found == 1
        assert summary.renamed == 0
        assert summary.failed == 0
        # nothing_found is an expected outcome, not a failure.
        assert summary.exit_code() == 0

    def test_to_dict(self):
        summary = EnrichSummary(
            total=5, resolved=3, nothing_found=1, renamed=2, already_resolved=1, failed=1
        )
        d = summary.to_dict()
        assert d["total"] == 5
        assert d["resolved"] == 3
        assert d["nothing_found"] == 1

    def test_exit_code(self):
        assert EnrichSummary(failed=0).exit_code() == 0
        assert EnrichSummary(failed=1).exit_code() == 2
