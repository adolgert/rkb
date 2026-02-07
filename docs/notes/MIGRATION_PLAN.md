# Migration Plan: Current State -> Component System

Goal:
- Preserve expensive existing conversions/indexing in `kbase`.
- Introduce canonical `content_sha256` identity and minimal command workflow.
- Avoid forced recomputation.

## Principles

1. Additive first, destructive last.
2. Verify every phase before advancing.
3. Preserve current extraction/index outputs until explicitly retired.

## Phase 0: Snapshot and Safety

1. Record baseline counts:
   - documents
   - extractions
   - embeddings
   - extracted `.mmd` files
2. Backup artifacts:
   - `rkb_documents.db`
   - `rkb_extractions/`
   - `rkb_chroma_db/`
3. Store backup manifest with timestamp and host.

Exit criteria:
- Backup verified readable.

## Phase 1: Schema Extension (No Behavior Change)

1. Add `content_sha256` and `canonical_pdf_path` to `documents` (nullable initially).
2. Add new tables:
   - `document_sources`
   - `conversions`
   - `chunk_runs`
   - `zotero_links`
   - `transfers`, `transfer_files`
3. Add non-unique index on `content_sha256`.

Exit criteria:
- Existing commands still run.
- New schema is present.

## Phase 2: Hash Backfill for Existing `kbase` Docs

1. For each `documents.source_path` that exists:
   - compute SHA-256
   - write `content_sha256`
2. For missing source files:
   - mark unresolved in audit table/log
   - do not delete existing records
3. Populate `document_sources` with current known `source_path`.

Exit criteria:
- High coverage of `content_sha256` (target >= 99% for existing source paths).
- Unresolved list produced.

## Phase 3: Canonical Store Build (No Re-Extraction)

1. Create canonical path for each resolved hash:
   - `raw/sha256/ab/cd/<hash>.pdf`
2. Copy/link best available source file into canonical store.
3. Backfill `documents.canonical_pdf_path`.

Notes:
- Prefer hardlinks when possible; fallback to copy.
- Never overwrite canonical file if existing hash verifies.

Exit criteria:
- Every resolved `content_sha256` has canonical file.

## Phase 4: Map Existing Extractions to `content_sha256`

1. Use `doc_id -> extraction_path` existing mapping.
2. Join to newly backfilled `content_sha256`.
3. Fill `conversions` entries for docs already extracted/indexed.

Important:
- Keep existing `rkb_extractions/documents/<uuid>/extracted.mmd` intact.
- Optionally materialize hash-keyed copies later.

Exit criteria:
- Existing extraction/index work is represented in new metadata tables.

## Phase 5: Import Legacy `findpdfs` Data

1. Read `findpdfs` path/hash inventory (legacy SHA-1 store).
2. Re-hash source files with SHA-256 where available.
3. Add discovered sources to `document_sources`.
4. Ingest unseen hashes into canonical store.

Exit criteria:
- `findpdfs` assets are reflected in canonical catalog without duplication.

## Phase 6: Implement Minimal Commands

Implementation order:
1. `pdf status`
2. `pdf sync`
3. `pdf export`
4. `pdf import`
5. `pdf convert`
6. `pdf index`
7. `pdf link-zotero`

Policy:
- Every command starts with `--dry-run` support.
- Idempotency tests required for each command.

Exit criteria:
- Daily routine can run entirely from minimal command surface.

## Phase 7: Enforce Hash Policy

1. Make `content_sha256` required for new ingests.
2. Add `UNIQUE(content_sha256)`.
3. Disallow SHA-1/MD5 identity usage in dedup paths.

Exit criteria:
- No new records missing `content_sha256`.
- Audit passes with zero hash-policy violations.

## Rollback Strategy

- If any phase fails, restore from Phase 0 backups.
- Keep migration scripts idempotent and reversible where possible.
- Never delete old data during active migration.

## Acceptance Checklist

- [ ] Existing `kbase` markdown corpus preserved and queryable.
- [ ] Canonical store complete for resolved docs.
- [ ] `pdf status` reflects true backlog and failures.
- [ ] Work->home transfer succeeds without duplicate growth.
- [ ] No unresolved hash mismatches.
