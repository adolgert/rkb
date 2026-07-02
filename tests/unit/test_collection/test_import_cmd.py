"""Tests for the import CLI command handler."""

import argparse
from pathlib import Path
from unittest.mock import patch

from rkb.cli.commands import import_cmd


def _make_args(**overrides):
    defaults = {"directories": [], "dry_run": False, "config": None, "verbose": False}
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_import_runs_steps_in_order(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    calls = []

    def _record(name, code=0):
        def _execute(namespace):
            calls.append((name, namespace))
            return code

        return _execute

    with (
        patch("rkb.cli.commands.ingest_cmd.execute", _record("ingest")),
        patch("rkb.cli.commands.translate_cmd.execute", _record("translate")),
        patch("rkb.cli.commands.index_cmd.execute", _record("index")),
    ):
        exit_code = import_cmd.execute(_make_args(directories=[tmp_path]))

    assert exit_code == 0
    assert [name for name, _ in calls] == ["ingest", "translate", "index"]

    ingest_namespace = calls[0][1]
    assert ingest_namespace.directories == [tmp_path]
    assert ingest_namespace.resolve is True
    assert ingest_namespace.dry_run is False

    stdout = capsys.readouterr().out
    assert "rkb recent" in stdout


def test_import_defaults_to_mendeley(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    calls = []

    def _execute(namespace):
        calls.append(namespace)
        return 0

    with (
        patch("rkb.cli.commands.ingest_cmd.execute", _execute),
        patch("rkb.cli.commands.translate_cmd.execute", lambda _ns: 0),
        patch("rkb.cli.commands.index_cmd.execute", lambda _ns: 0),
    ):
        exit_code = import_cmd.execute(_make_args())

    assert exit_code == 0
    assert calls[0].directories == [Path("~/Dropbox/Mendeley").expanduser()]


def test_import_returns_worst_exit_code_and_still_runs_all_steps(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    calls = []

    def _record(name, code):
        def _execute(namespace):
            calls.append(name)
            return code

        return _execute

    with (
        patch("rkb.cli.commands.ingest_cmd.execute", _record("ingest", 0)),
        patch("rkb.cli.commands.translate_cmd.execute", _record("translate", 1)),
        patch("rkb.cli.commands.index_cmd.execute", _record("index", 0)),
    ):
        exit_code = import_cmd.execute(_make_args(directories=[tmp_path]))

    assert exit_code == 1
    assert calls == ["ingest", "translate", "index"]
    assert "FAILED" in capsys.readouterr().out


def test_import_dry_run_propagates(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    namespaces = []

    def _execute(namespace):
        namespaces.append(namespace)
        return 0

    with (
        patch("rkb.cli.commands.ingest_cmd.execute", _execute),
        patch("rkb.cli.commands.translate_cmd.execute", _execute),
        patch("rkb.cli.commands.index_cmd.execute", _execute),
    ):
        exit_code = import_cmd.execute(_make_args(directories=[tmp_path], dry_run=True))

    assert exit_code == 0
    assert all(namespace.dry_run for namespace in namespaces)


def test_import_errors_without_gemini_key(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # no local.env here

    exit_code = import_cmd.execute(_make_args(directories=[tmp_path]))
    stdout = capsys.readouterr().out

    assert exit_code == 1
    assert "GEMINI_API_KEY" in stdout


def test_import_loads_local_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "local.env").write_text(
        "# comment\n"
        "GEMINI_API_KEY=from-file\n"
        'ANTHROPIC_API_KEY="quoted-key"\n'
        "export S2_API_KEY=exported\n"
    )

    import os

    clean_env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    with (
        patch.dict(os.environ, clean_env, clear=True),
        patch("rkb.cli.commands.ingest_cmd.execute", lambda _ns: 0),
        patch("rkb.cli.commands.translate_cmd.execute", lambda _ns: 0),
        patch("rkb.cli.commands.index_cmd.execute", lambda _ns: 0),
    ):
        exit_code = import_cmd.execute(_make_args(directories=[tmp_path]))
        assert os.environ["GEMINI_API_KEY"] == "from-file"
        assert os.environ["ANTHROPIC_API_KEY"] == "quoted-key"
        assert os.environ["S2_API_KEY"] == "exported"

    assert exit_code == 0
