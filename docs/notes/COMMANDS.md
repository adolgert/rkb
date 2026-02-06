# Command Surface (Minimal, Stable)

This document defines the small command surface for the consolidated PDF pipeline.

Goals:

1. Easy to remember.
2. Safe to rerun (idempotent).
3. Predictable output for humans and scripts.

## Global CLI Conventions

- All commands must support `--dry-run` (no mutations).
- All commands must support `--json` (machine-readable output).
- Exit codes:
  - `0`: success
  - `1`: operational error (invalid input, missing file, runtime failure)
  - `2`: partial success (some items failed; details in output)
- Standard identity field in output: `content_sha256`.
- Timestamps use ISO 8601 UTC.

## Command Group

The preferred long-term surface is a dedicated command group:

```bash
pdf <command> [options]
```

During transition, these can be implemented under `rkb` as aliases (`rkb pdf ...`).

## `pdf sync`

Responsibility:
- Discovery + ingest for local machine roots.

Usage:

```bash
pdf sync
pdf sync --roots ~/Downloads ~/Zotero/storage ~/Dropbox ~/Dropbox/Mendeley ~/Dropbox/books
pdf sync --machine-id home-desktop --json
```

Required behavior:
- Recursively discover PDFs in roots.
- Compute `content_sha256`.
- Ingest only unseen hashes into canonical store.
- Record source paths in source ledger.
- Never convert/index in this command.

Required output fields:
- `discovered_count`
- `new_canonical_count`
- `existing_count`
- `failed_count`
- `failures[]` (path + error)

## `pdf export`

Responsibility:
- Create transfer package for work -> home movement.

Usage:

```bash
pdf export --to ~/Box/findpdfs-outbox/work-2026-02-06.zip
pdf export --since 2026-02-01 --to ~/Box/findpdfs-outbox/week1.zip
pdf export --manifest-only --to ~/Box/findpdfs-outbox/week1.manifest.json
```

Required behavior:
- Select docs by status/time filter.
- Write manifest with `content_sha256`, source hints, and relative archive path.
- Optional zip includes canonical PDFs.
- Export is idempotent for same selection.

Required output fields:
- `manifest_path`
- `archive_path` (nullable)
- `file_count`
- `total_bytes`

## `pdf import`

Responsibility:
- Import manifest/zip and ingest into canonical store.

Usage:

```bash
pdf import ~/Box/findpdfs-outbox/work-2026-02-06.zip
pdf import ~/Box/findpdfs-outbox/week1.manifest.json --from-dir ~/Box/findpdfs-outbox/week1-files
```

Required behavior:
- Validate manifest format/version.
- Verify file hash before ingest.
- Ingest unseen hashes only.
- Register transfer and import status.

Required output fields:
- `imported_new_count`
- `already_present_count`
- `hash_mismatch_count`
- `failed_count`

## `pdf convert`

Responsibility:
- Canonical PDF -> markdown artifacts.

Usage:

```bash
pdf convert --only-new
pdf convert --doc-sha256 <hash>
pdf convert --retry-failed
```

Required behavior:
- Read canonical PDFs only.
- Write both artifacts:
  - `mmd/raw/<content_sha256>.mmd`
  - `mmd/clean/<content_sha256>.md`
- Record converter versions and status.
- Skip already-successful docs unless forced.

Required output fields:
- `converted_count`
- `skipped_count`
- `failed_count`
- `failure_reasons[]`

## `pdf index`

Responsibility:
- Chunk + embed converted markdown.

Usage:

```bash
pdf index --only-new
pdf index --doc-sha256 <hash>
```

Required behavior:
- Read `mmd/clean` only.
- Produce chunk records with required citation metadata.
- Build/update vector index.

Required output fields:
- `indexed_count`
- `chunk_count`
- `failed_count`

## `pdf link-zotero`

Responsibility:
- Link docs to Zotero; optionally copy canonical PDFs into Zotero.

Usage:

```bash
pdf link-zotero --only-unlinked
pdf link-zotero --mode copy --only-unlinked
```

Modes:
- `record-only`: write link metadata only.
- `copy`: copy canonical PDF to Zotero attachment storage and record attachment key.

Required behavior:
- Zotero is metadata/readability mirror.
- Canonical store remains source of truth.

Required output fields:
- `linked_count`
- `copied_count`
- `unmatched_count`
- `failed_count`

## `pdf status`

Responsibility:
- One-page health view.

Usage:

```bash
pdf status
pdf status --json
```

Must include:
- Stage counts: discovered, canonical, converted, indexed, failed.
- Backlogs:
  - canonical-not-converted
  - converted-not-indexed
- Recent failures and retry hint.
- Hash policy violations (if any).

## Non-Goals for this Surface

- No one-off ad hoc commands in daily workflow.
- No command that mixes multiple lifecycle stages beyond `sync` (discovery+ingest only).
