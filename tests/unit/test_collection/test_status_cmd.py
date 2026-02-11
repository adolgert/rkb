"""Tests for the status CLI command handler."""

import argparse
import json

from rkb.cli.commands import status_cmd
from rkb.collection.config import CollectionConfig
from rkb.collection.ingest import ingest_directories


def test_status_execute_json_output_with_catalog_data(monkeypatch, tmp_path, capsys):
    library_root = tmp_path / "library"
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "paper.pdf").write_bytes(b"status bytes")

    monkeypatch.setenv("PDF_LIBRARY_ROOT", str(library_root))
    monkeypatch.setenv("PDF_MACHINE_ID", "status-test-machine")

    config = CollectionConfig.load()
    ingest_directories(
        directories=[inbox],
        config=config,
        dry_run=False,
        skip_zotero=True,
        no_display_name=True,
    )

    args = argparse.Namespace(
        json=True,
        recent=10,
        config=None,
        verbose=False,
    )
    exit_code = status_cmd.execute(args)
    stdout = capsys.readouterr().out
    payload = json.loads(stdout)

    assert exit_code == 0
    assert payload["canonical_files"] == 1
    assert payload["zotero_linked_files"] == 0
    assert payload["unlinked_files"] == 1
    assert payload["canonical_store_bytes"] > 0
    assert len(payload["recent_ingest"]) >= 1


def test_status_execute_json_output_without_catalog(monkeypatch, tmp_path, capsys):
    library_root = tmp_path / "library"
    monkeypatch.setenv("PDF_LIBRARY_ROOT", str(library_root))
    monkeypatch.setenv("PDF_MACHINE_ID", "status-test-machine")

    args = argparse.Namespace(
        json=True,
        recent=5,
        config=None,
        verbose=False,
    )
    exit_code = status_cmd.execute(args)
    stdout = capsys.readouterr().out
    payload = json.loads(stdout)

    assert exit_code == 0
    assert payload["canonical_files"] == 0
    assert payload["zotero_linked_files"] == 0
    assert payload["unlinked_files"] == 0
    assert payload["recent_ingest"] == []
