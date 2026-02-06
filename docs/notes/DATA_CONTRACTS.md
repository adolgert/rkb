# Data Contracts

This document defines authoritative identities, file layout contracts, and schema contracts for a predictable pipeline.

## 1) Identity Contract

Canonical identity:
- `content_sha256`: lowercase SHA-256 hex digest of canonical PDF bytes.

Rules:
1. Dedup decisions use only `content_sha256`.
2. Transfer manifests identify files by `content_sha256`.
3. Conversion/index artifacts are keyed by `content_sha256`.
4. `sha1` and `md5` are legacy-only fields and must never determine identity.

Compatibility with existing `kbase`:
- Existing `documents.doc_id` (UUID) remains supported.
- Add authoritative `documents.content_sha256` and unique index.
- Use mapping `doc_id <-> content_sha256` for backward compatibility.

## 2) Filesystem Contract

Library root (`$LIBRARY_ROOT`):

```text
$LIBRARY_ROOT/
  raw/sha256/ab/cd/<content_sha256>.pdf
  mmd/raw/<content_sha256>.mmd
  mmd/clean/<content_sha256>.md
  chunks/<content_sha256>.jsonl
  manifests/
  transfer/{outbox,inbox}/
  db/catalog.sqlite
  logs/
```

Rules:
- `raw/sha256` files are immutable.
- Downstream files may be regenerated.
- A missing downstream file is recoverable from canonical PDF.

## 3) SQLite Schema Contracts (Additive)

These can be implemented in existing `rkb_documents.db` or in a dedicated catalog DB.

### `documents` (existing, extended)

Required columns:
- `doc_id TEXT PRIMARY KEY` (legacy UUID supported)
- `content_sha256 TEXT` (required after migration)
- `canonical_pdf_path TEXT`
- `status TEXT`
- `added_date TEXT`
- `updated_date TEXT`

Required index:
- `UNIQUE(content_sha256)` once backfill completes.

### `document_sources` (new)

Purpose:
- Track all seen source paths for same content.

Columns:
- `source_id TEXT PRIMARY KEY`
- `content_sha256 TEXT NOT NULL`
- `machine_id TEXT NOT NULL`
- `source_path TEXT NOT NULL`
- `first_seen TEXT NOT NULL`
- `last_seen TEXT NOT NULL`
- `source_type TEXT` (`downloads|zotero|dropbox|box|other`)

Recommended index:
- `INDEX(content_sha256)`
- `INDEX(machine_id, source_path)`

### `conversions` (new)

Purpose:
- Track markdown conversion status/version.

Columns:
- `content_sha256 TEXT PRIMARY KEY`
- `raw_mmd_path TEXT`
- `clean_md_path TEXT`
- `converter_name TEXT`
- `converter_version TEXT`
- `cleaner_version TEXT`
- `status TEXT` (`pending|complete|failed`)
- `error_message TEXT`
- `updated_at TEXT`

### `chunk_runs` (new)

Purpose:
- Track chunk/index generation versions.

Columns:
- `content_sha256 TEXT PRIMARY KEY`
- `chunk_path TEXT`
- `chunker_version TEXT`
- `embedder_name TEXT`
- `embedder_version TEXT`
- `index_status TEXT` (`pending|complete|failed`)
- `error_message TEXT`
- `updated_at TEXT`

### `zotero_links` (new)

Purpose:
- Link canonical docs to Zotero records.

Columns:
- `content_sha256 TEXT NOT NULL`
- `zotero_item_key TEXT NOT NULL`
- `zotero_attachment_key TEXT`
- `link_mode TEXT` (`record-only|copy`)
- `linked_at TEXT NOT NULL`

Primary key:
- `(content_sha256, zotero_item_key)`

### `transfers` and `transfer_files` (new)

`transfers`:
- `transfer_id TEXT PRIMARY KEY`
- `manifest_path TEXT`
- `archive_path TEXT`
- `source_machine_id TEXT`
- `created_at TEXT`
- `imported_at TEXT`

`transfer_files`:
- `transfer_id TEXT NOT NULL`
- `content_sha256 TEXT NOT NULL`
- `archive_relpath TEXT`
- `bytes INTEGER`
- Primary key `(transfer_id, content_sha256)`

## 4) Manifest Contract (v1)

`manifest.json`:

```json
{
  "manifest_version": "1.0",
  "transfer_id": "uuid",
  "source_machine_id": "work-laptop",
  "created_at": "2026-02-06T20:30:00Z",
  "files": [
    {
      "content_sha256": "<hex>",
      "archive_relpath": "ab/cd/<hex>.pdf",
      "bytes": 1234567,
      "source_hint": "/home/user/Downloads/paper.pdf"
    }
  ]
}
```

Validation requirements:
- `manifest_version` must be recognized.
- `content_sha256` must match file bytes at import time.

## 5) Chunk Contract for LLM Citation

Each chunk record in `chunks/<content_sha256>.jsonl` must include:
- `content_sha256`
- `chunk_id`
- `text`
- `page_start`
- `page_end`
- `section_path`
- `has_equations`
- `chunker_version`

Citation requirement:
- Retrieval answers must reference `content_sha256` + `page_start/page_end` + `chunk_id`.

## 6) Backward Compatibility Contract

- Existing `rkb_extractions/documents/<uuid>/extracted.mmd` remains valid.
- New canonical naming by `content_sha256` is additive.
- No destructive migration before verification reports are clean.
