"""Tests for the zotero-push CLI command handler (pyzotero client mocked)."""

from __future__ import annotations

import argparse
import json
from unittest.mock import MagicMock, patch

from rkb.cli.commands import zotero_push_cmd
from rkb.collection.catalog import Catalog


def _make_args(**overrides):
    defaults = {"limit": 50, "dry_run": False, "json": False, "config": None, "verbose": False}
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _seed(library_root, tmp_path, sha, *, title="A Paper"):
    catalog = Catalog(library_root / "db" / "pdf_catalog.db")
    catalog.initialize()
    pdf_path = tmp_path / f"{sha}.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    catalog.add_canonical_file(
        content_sha256=sha,
        canonical_path=str(pdf_path),
        display_name=f"{sha[:6]}.pdf",
        original_filename="orig.pdf",
        page_count=1,
        file_size_bytes=10,
    )
    if title is not None:
        catalog.set_resolved_metadata(
            sha, title=title, authors=["Someone"], year=2022,
            journal="J", abstract="a", doc_type="journal-article",
        )
    catalog.close()


def test_dry_run_makes_no_client_calls(monkeypatch, tmp_path, capsys):
    library_root = tmp_path / "library"
    monkeypatch.setenv("PDF_LIBRARY_ROOT", str(library_root))
    _seed(library_root, tmp_path, "a" * 64, title="Titled Paper")
    _seed(library_root, tmp_path, "b" * 64, title=None)

    with patch("rkb.collection.runtime.build_zotero_client") as build_client:
        exit_code = zotero_push_cmd.execute(_make_args(dry_run=True))

    stdout = capsys.readouterr().out
    assert exit_code == 0
    build_client.assert_not_called()
    assert "Would push 1 item" in stdout
    assert "Skipped (no resolved title): 1" in stdout
    assert "Titled Paper" in stdout


def test_dry_run_json(monkeypatch, tmp_path, capsys):
    library_root = tmp_path / "library"
    monkeypatch.setenv("PDF_LIBRARY_ROOT", str(library_root))
    _seed(library_root, tmp_path, "a" * 64, title="Titled Paper")

    exit_code = zotero_push_cmd.execute(_make_args(dry_run=True, json=True))
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["dry_run"] is True
    assert payload["would_push"] == 1
    assert payload["skipped_no_metadata"] == 0
    assert payload["preview"] == ["Titled Paper"]


def test_execute_happy_path_exit_zero(monkeypatch, tmp_path, capsys):
    library_root = tmp_path / "library"
    monkeypatch.setenv("PDF_LIBRARY_ROOT", str(library_root))
    _seed(library_root, tmp_path, "a" * 64)

    zot = MagicMock()
    zot.create_items.return_value = {"successful": {"0": {"key": "IK"}}}
    zot.attachment_simple.return_value = {"successful": {"0": {"key": "AK"}}}

    with patch("rkb.collection.runtime.build_zotero_client", return_value=zot):
        exit_code = zotero_push_cmd.execute(_make_args(json=True))

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["pushed"] == 1
    assert payload["failed"] == 0


def test_execute_partial_failure_exit_two(monkeypatch, tmp_path, capsys):
    library_root = tmp_path / "library"
    monkeypatch.setenv("PDF_LIBRARY_ROOT", str(library_root))
    _seed(library_root, tmp_path, "a" * 64)

    zot = MagicMock()
    zot.create_items.side_effect = RuntimeError("boom")

    with patch("rkb.collection.runtime.build_zotero_client", return_value=zot):
        exit_code = zotero_push_cmd.execute(_make_args())

    stdout = capsys.readouterr().out
    assert exit_code == 2
    assert "Failed:" in stdout


def test_execute_credential_error_exit_one(monkeypatch, tmp_path, capsys):
    library_root = tmp_path / "library"
    monkeypatch.setenv("PDF_LIBRARY_ROOT", str(library_root))
    monkeypatch.delenv("ZOTERO_LIBRARY_ID", raising=False)
    monkeypatch.delenv("ZOTERO_API_KEY", raising=False)
    # cwd must not contain a local.env, or execute() reloads real credentials
    # and the push runs against the live Zotero library.
    monkeypatch.chdir(tmp_path)
    _seed(library_root, tmp_path, "a" * 64)

    exit_code = zotero_push_cmd.execute(_make_args())
    stdout = capsys.readouterr().out

    assert exit_code == 1
    assert "Zotero push failed" in stdout
