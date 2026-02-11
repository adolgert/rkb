"""Tests for the rectify CLI command handler."""

import argparse
import json
from pathlib import Path

from rkb.cli.commands import rectify_cmd


def test_rectify_execute_json_output(monkeypatch, tmp_path, capsys):
    library_root = tmp_path / "library"
    scan_dir = tmp_path / "scan"
    scan_dir.mkdir()
    (scan_dir / "paper.pdf").write_bytes(b"cli bytes")

    monkeypatch.setenv("PDF_LIBRARY_ROOT", str(library_root))
    monkeypatch.setenv("PDF_MACHINE_ID", "cli-test-machine")
    monkeypatch.setenv("PDF_ZOTERO_STORAGE", str(tmp_path / "zotero-empty"))

    args = argparse.Namespace(
        scan=[scan_dir],
        dry_run=False,
        report=False,
        skip_zotero=True,
        json=True,
        config=None,
        verbose=False,
    )

    exit_code = rectify_cmd.execute(args)
    stdout = capsys.readouterr().out
    payload = json.loads(stdout)

    assert exit_code == 0
    assert payload["scanned_directories"] == 1
    assert payload["total_files_found"] == 1
    assert payload["copied_to_canonical"] == 1
    assert payload["failed"] == 0


def test_rectify_execute_returns_1_on_operational_error(capsys):
    args = argparse.Namespace(
        scan=[Path("/definitely/missing/directory")],
        dry_run=False,
        report=False,
        skip_zotero=True,
        json=False,
        config=None,
        verbose=False,
    )

    exit_code = rectify_cmd.execute(args)
    stdout = capsys.readouterr().out

    assert exit_code == 1
    assert "Rectify failed" in stdout
