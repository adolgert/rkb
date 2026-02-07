"""Flask application for local PDF triage on the work machine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import Flask, g, jsonify, render_template, request

from rkb.collection.hashing import hash_file_sha256
from rkb.triage.decisions import TriageDecisionStore
from rkb.triage.pdf_renderer import get_page_count, render_pdf_pages_base64
from rkb.triage.staging import remove_staged_file, stage_approved_file


def _scan_downloads(
    downloads_dir: Path,
    store: TriageDecisionStore,
    *,
    recursive: bool = False,
) -> list[dict[str, Any]]:
    iterator = downloads_dir.rglob("*.pdf") if recursive else downloads_dir.glob("*.pdf")
    pdf_paths = sorted(
        (path for path in iterator if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    scanned_entries: list[dict[str, Any]] = []
    hashes: list[str] = []

    for pdf_path in pdf_paths:
        content_sha256 = hash_file_sha256(pdf_path)
        hashes.append(content_sha256)
        scanned_entries.append(
            {
                "content_sha256": content_sha256,
                "path": str(pdf_path),
                "filename": pdf_path.name,
                "file_size_bytes": pdf_path.stat().st_size,
                "page_count": get_page_count(pdf_path),
                "modified_epoch": pdf_path.stat().st_mtime,
            }
        )

    decisions_map = store.get_decisions_map(hashes)
    for entry in scanned_entries:
        decision_row = decisions_map.get(entry["content_sha256"])
        entry["decision"] = decision_row["decision"] if decision_row else "undecided"
        entry["staged_path"] = decision_row["staged_path"] if decision_row else None

    return scanned_entries


def create_app(
    downloads_dir: Path,
    staging_dir: Path,
    db_path: Path,
    *,
    recursive_scan: bool = False,
) -> Flask:
    """Create and configure the triage Flask app."""
    app = Flask(__name__)
    app.config["downloads_dir"] = downloads_dir
    app.config["staging_dir"] = staging_dir
    app.config["triage_db_path"] = db_path
    app.config["triage_recursive_scan"] = recursive_scan

    def _get_store() -> TriageDecisionStore:
        store = g.get("triage_store")
        if store is None:
            store = TriageDecisionStore(db_path)
            store.initialize()
            g.triage_store = store
        return store

    @app.teardown_appcontext
    def _close_store(_error: Exception | None) -> None:
        store = g.pop("triage_store", None)
        if store is not None:
            store.close()

    @app.get("/")
    def review() -> str:
        decision_filter = request.args.get("filter", "all")
        files = _scan_downloads(
            downloads_dir,
            _get_store(),
            recursive=app.config["triage_recursive_scan"],
        )

        if decision_filter != "all":
            files = [entry for entry in files if entry["decision"] == decision_filter]

        return render_template(
            "review.html",
            files=files,
            decision_filter=decision_filter,
        )

    @app.get("/pdf/<content_sha256>/pages")
    def pdf_pages(content_sha256: str):
        path_value = request.args.get("path")
        store = _get_store()
        if path_value:
            source_path = Path(path_value)
        else:
            row = store.get_decision(content_sha256)
            if row is None:
                return jsonify({"error": "Unknown file"}), 404
            source_path = Path(row["original_path"])

        if not source_path.exists():
            return jsonify({"error": "Source file no longer exists"}), 404

        images = render_pdf_pages_base64(source_path, max_pages=2)
        return jsonify({"pages": images})

    @app.post("/pdf/<content_sha256>/decide")
    def decide(content_sha256: str):
        decision = request.form.get("decision")
        if request.is_json:
            payload = request.get_json(silent=True) or {}
            decision = payload.get("decision", decision)
            source_path_value = payload.get("path")
        else:
            source_path_value = request.form.get("path")

        if decision not in {"approved", "rejected"}:
            return jsonify({"error": "Invalid decision"}), 400
        if not source_path_value:
            return jsonify({"error": "Missing source path"}), 400

        source_path = Path(source_path_value)
        if not source_path.exists():
            return jsonify({"error": "Source file not found"}), 404

        store = _get_store()
        current = store.get_decision(content_sha256)
        previous_staged = current["staged_path"] if current else None

        staged_path: str | None = None
        if decision == "approved":
            staged = stage_approved_file(
                source_path=source_path,
                original_filename=source_path.name,
                content_sha256=content_sha256,
                staging_dir=staging_dir,
            )
            staged_path = str(staged)
        else:
            remove_staged_file(previous_staged)

        store.set_decision(
            content_sha256=content_sha256,
            decision=decision,
            original_path=str(source_path),
            original_filename=source_path.name,
            file_size_bytes=source_path.stat().st_size,
            page_count=get_page_count(source_path),
            staged_path=staged_path,
        )

        return jsonify(
            {
                "ok": True,
                "content_sha256": content_sha256,
                "decision": decision,
                "staged_path": staged_path,
            }
        )

    @app.get("/queue")
    def queue() -> str:
        store = _get_store()
        approved = store.list_approved()
        return render_template("queue.html", approved=approved)

    @app.get("/history")
    def history() -> str:
        store = _get_store()
        decision_filter = request.args.get("decision")
        rows = store.list_history(decision=decision_filter)
        return render_template("history.html", history_rows=rows, decision_filter=decision_filter)

    @app.get("/api/stats")
    def api_stats():
        files = _scan_downloads(
            downloads_dir,
            _get_store(),
            recursive=app.config["triage_recursive_scan"],
        )
        stats = {
            "undecided": len([entry for entry in files if entry["decision"] == "undecided"]),
            "approved": len([entry for entry in files if entry["decision"] == "approved"]),
            "rejected": len([entry for entry in files if entry["decision"] == "rejected"]),
            "transferred": 0,
        }
        return jsonify(stats)

    return app
