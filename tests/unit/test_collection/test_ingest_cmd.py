"""Tests for the ingest CLI command handler."""

import argparse
import json
from pathlib import Path

from rkb.cli.commands import ingest_cmd


def test_ingest_execute_json_output(monkeypatch, tmp_path, capsys):
    library_root = tmp_path / "library"
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "paper.pdf").write_bytes(b"cli bytes")

    monkeypatch.setenv("PDF_LIBRARY_ROOT", str(library_root))
    monkeypatch.setenv("PDF_MACHINE_ID", "cli-test-machine")

    args = argparse.Namespace(
        directories=[inbox],
        dry_run=False,
        skip_zotero=True,
        no_display_name=True,
        json=True,
        config=None,
        verbose=False,
    )

    exit_code = ingest_cmd.execute(args)
    stdout = capsys.readouterr().out
    payload = json.loads(stdout)

    assert exit_code == 0
    assert payload["scanned"] == 1
    assert payload["new"] == 1
    assert payload["failed"] == 0


def test_ingest_execute_returns_1_on_operational_error(capsys):
    args = argparse.Namespace(
        directories=[Path("/definitely/missing/directory")],
        dry_run=False,
        skip_zotero=True,
        no_display_name=True,
        json=False,
        config=None,
        verbose=False,
    )

    exit_code = ingest_cmd.execute(args)
    stdout = capsys.readouterr().out

    assert exit_code == 1
    assert "Ingest failed" in stdout

