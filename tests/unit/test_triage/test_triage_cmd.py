"""Tests for triage CLI command behavior."""

import argparse

from rkb.cli.commands import triage_cmd


def test_triage_cmd_rebuild_staging(monkeypatch, tmp_path, capsys):
    staging = tmp_path / "staging"
    downloads = tmp_path / "downloads"
    staging.mkdir()
    downloads.mkdir()

    monkeypatch.setenv("PDF_BOX_STAGING", str(staging))
    monkeypatch.setenv("PDF_WORK_DOWNLOADS", str(downloads))

    args = argparse.Namespace(
        port=5000,
        downloads=None,
        staging=None,
        rebuild_staging=True,
        recursive=False,
        config=None,
        verbose=False,
    )

    exit_code = triage_cmd.execute(args)
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Rebuild complete" in output
