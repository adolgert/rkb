# findpdfs Components and Minimal Command Surface

This document defines a concrete, low-memory workflow for consolidating PDFs across machines and producing LLM-ready Markdown.

The core requirement is simple:

1. One source of truth for PDF bytes.
2. One content ID everywhere (`sha256`).
3. Small command surface, safe to rerun.

## 1) Canonical Data Model

### Identity

- `doc_id` is always the lowercase hex SHA-256 hash of canonical PDF bytes.
- Store as `sha256:<hex>` in external manifests if a prefixed form is needed.
- Legacy hashes (`sha1`, `md5`) may be kept only for migration lookup and must not be used for dedup decisions.

### Canonical layout

Use one library root (`$LIBRARY_ROOT`), for example `~/Dropbox/findpdfs-library`:

```text
$LIBRARY_ROOT/
  raw/
    sha256/
      ab/cd/
        abcdef...1234.pdf
  mmd/
    raw/
      abcdef...1234.mmd
    clean/
      abcdef...1234.md
  chunks/
    abcdef...1234.jsonl
  transfer/
    outbox/
    inbox/
  manifests/
  db/
    catalog.sqlite
  logs/
```

Rules:

- `raw/sha256/.../*.pdf` is immutable and authoritative.
- All downstream artifacts are keyed by `doc_id`.
- Zotero attachments are optional mirrors, never authority.

## 2) Components (One Responsibility Each)

## Component A: Discovery

Responsibility:
- Find candidate PDFs on a machine.

Inputs:
- Local roots (Downloads, Zotero storage, Dropbox folders, etc.).

Outputs:
- Discovery records: `machine_id`, `source_path`, `size`, `mtime`, `sha256`, `scan_time`.

Constraints:
- No copying, no deleting, no conversion.

## Component B: Ingest and Dedup

Responsibility:
- Copy only new content hashes into canonical store.

Inputs:
- Discovery records and accessible source files.

Outputs:
- Canonical PDFs under `raw/sha256/...`.
- Catalog entries in `db/catalog.sqlite`.

Constraints:
- Idempotent: rerun does nothing for already-ingested hashes.
- Dedup decision uses only `sha256`.

## Component C: Transfer Bridge (work -> home)

Responsibility:
- Package and move files across constrained environments.

Inputs:
- Work machine catalog + source files.

Outputs:
- `manifest.json` plus optional zip in `transfer/outbox/` (Box-shared location).

Constraints:
- No conversion or indexing.
- Import side does dedup by `sha256`.

## Component D: Conversion (PDF -> Markdown)

Responsibility:
- Produce deterministic Markdown from canonical PDFs.

Inputs:
- Canonical PDFs in `raw/sha256`.

Outputs:
- `mmd/raw/<doc_id>.mmd` (extractor output).
- `mmd/clean/<doc_id>.md` (normalized for retrieval).
- Conversion status in catalog.

Constraints:
- Conversion never discovers or imports files.
- Safe to rerun by `doc_id`.

## Component E: Chunking

Responsibility:
- Turn cleaned Markdown into citeable chunks.

Inputs:
- `mmd/clean/<doc_id>.md`.

Outputs:
- `chunks/<doc_id>.jsonl` with chunk metadata.

Required chunk metadata:
- `doc_id`, `chunk_id`, `page_start`, `page_end`, `section_path`, `has_equations`.

## Component F: Index/Search

Responsibility:
- Build and query vector index from chunks.

Inputs:
- Chunk JSONL.

Outputs:
- Vector index and retrieval API/CLI output.

Constraints:
- Indexing never mutates source PDFs or Markdown.

## Component G: Metadata Linker (Zotero)

Responsibility:
- Link bibliographic items to `doc_id`.

Inputs:
- Zotero item metadata + catalog.

Outputs:
- Link table: `zotero_item_key`, `zotero_attachment_key`, `doc_id`, `link_mode`.

Policy:
- Allowed: copy canonical PDF into Zotero for reading convenience.
- Not allowed: Zotero attachment bytes becoming source of truth.

## Component H: Audit and Status

Responsibility:
- Validate system health and drift.

Checks:
- Missing canonical files referenced by catalog.
- Missing Markdown/chunks for converted/indexed docs.
- Hash mismatches (canonical vs copied artifacts where applicable).
- Backlog counts by stage.

Outputs:
- Human-readable and JSON status reports.

## 3) Minimal Command Surface

Keep the interface intentionally small:

## `pdf sync`

Purpose:
- Run Discovery + Ingest for local machine roots.

Typical use:
```bash
pdf sync
pdf sync --roots ~/Downloads ~/Zotero/storage ~/Dropbox ~/Dropbox/Mendeley ~/Dropbox/books
```

Guarantees:
- No duplicate canonical files.
- Safe to run repeatedly.

## `pdf export`

Purpose:
- On work machine, package new canonical docs for Box transfer.

Typical use:
```bash
pdf export --to ~/Box/findpdfs-outbox/work-2026-02-06.zip
```

Guarantees:
- Exports by `sha256` manifest.
- Does not mark imported; only exported.

## `pdf import`

Purpose:
- On home machine, ingest transfer package from Box.

Typical use:
```bash
pdf import ~/Box/findpdfs-outbox/work-2026-02-06.zip
```

Guarantees:
- Dedup by `sha256`.
- Idempotent on repeated imports.

## `pdf convert`

Purpose:
- Convert canonical PDFs to Markdown.

Typical use:
```bash
pdf convert
pdf convert --only-new
pdf convert --retry-failed
```

Guarantees:
- Writes `mmd/raw` and `mmd/clean` keyed by `doc_id`.
- Does not re-convert successful docs unless forced.

## `pdf index`

Purpose:
- Chunk and index converted docs.

Typical use:
```bash
pdf index --only-new
```

Guarantees:
- Uses only `mmd/clean`.
- Stores chunk metadata needed for citations.

## `pdf link-zotero`

Purpose:
- Sync links between catalog docs and Zotero items; optionally copy canonical PDFs into Zotero.

Typical use:
```bash
pdf link-zotero --mode copy --only-unlinked
```

Guarantees:
- Updates link table only.
- Canonical store remains authority.

## `pdf status`

Purpose:
- Show one-page operational status.

Typical use:
```bash
pdf status
pdf status --json
```

Must include:
- Counts: discovered, canonical, converted, indexed, failed.
- Backlog: canonical-not-converted, converted-not-indexed.
- Recent failures with retry hint.

## 4) Operator Routine (Forget-Proof)

Daily on any machine:

```bash
pdf sync
```

When moving files from work to home:

```bash
# work machine
pdf sync
pdf export --to ~/Box/findpdfs-outbox/work-YYYY-MM-DD.zip

# home machine
pdf import ~/Box/findpdfs-outbox/work-YYYY-MM-DD.zip
```

Daily or nightly on home desktop:

```bash
pdf convert --only-new
pdf index --only-new
```

Weekly:

```bash
pdf status
pdf link-zotero --mode copy --only-unlinked
```

## 5) Contract Requirements for LLM Research Use

- Every answer must cite `doc_id` and page range from chunk metadata.
- No uncited responses in research mode.
- Keep both `raw.mmd` and `clean.md` for traceability.
- Record versions for extractor, cleaner, chunker, and embedder per doc/chunk.
- Reproducibility: any indexed chunk can be traced back to canonical PDF hash.

## 6) Migration Notes (from current state)

1. Standardize dedup and catalog IDs on SHA-256 immediately.
2. Keep old SHA-1/MD5 values only as optional legacy columns.
3. Add an audit check that flags any record missing SHA-256.
4. Migrate existing extracted markdown by mapping old records to `doc_id` where possible.
5. Do not delete legacy stores until `pdf status` shows no unresolved migration gaps.
