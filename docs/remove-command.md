# `rkb remove` — Remove a PDF from the Collection

## Purpose

The `remove` command deletes a single PDF and all its associated data from the
canonical library. Use it to discard image-only scans, blank forms, product
manuals, or supplementary appendices that have no usable text and only waste
processing time.

## Syntax

```
rkb remove <title-fragment | sha256-prefix> [--force] [--db-path PATH]
```

| Positional | Description |
|------------|-------------|
| `TITLE_OR_HASH` | One or more words matched against `display_name`, **or** a sha256 hex prefix (≥ 6 chars), **or** the full 64-character sha256 hash. Multiple words are joined and treated as one search string. |

| Flag | Default | Description |
|------|---------|-------------|
| `--force`, `-f` | off | Skip the "Delete? [y/N]" confirmation prompt. Useful in scripts. |
| `--db-path PATH` | `rkb_documents.db` (CWD) | Path to the project working-database (`rkb_documents.db`). |

## Examples

### Single title match — interactive confirmation

```
$ rkb remove Slesnick
  Name:   Slesnick 2021 Stellar Winds.pdf
  Hash:   3fa8c2d19e4b7601...
  Path:   ~/Dropbox/findpdfs-library/sha256/3f/a8/3fa8c2d19e4b7601.../
  Size:   1,204,736 bytes
  Pages:  12

Delete? [y/N] y
Removed: Slesnick 2021 Stellar Winds.pdf (3fa8c2d19e4b7601...)
```

### Ambiguous title — disambiguation table

```
$ rkb remove "submission 2019"
Found 2 matching PDFs:

  display_name                                        sha256               size       pages
  ------------------------------------------------    ------------------   ----------  -----
  Appendix 1 submission 2019.pdf                      a1b2c3d4e5f60001...     432,128      4
  Appendix 2 submission 2019.pdf                      a1b2c3d4e5f60002...     518,400      6

Refine your query or use the sha256 prefix.
```

### sha256 prefix — force-delete (no prompt)

```
$ rkb remove a1b2c3d4e5f60001 --force
  Name:   Appendix 1 submission 2019.pdf
  ...
Removed: Appendix 1 submission 2019.pdf (a1b2c3d4e5f60001...)
```

### Scripting — pipe-safe with `--force`

```bash
rkb remove "FORM-W9-blank" --force && echo "done"
```

## What Gets Deleted

Deletion is permanent and touches three locations:

### 1. Filesystem

```
~/Dropbox/findpdfs-library/sha256/<AA>/<BB>/<full-hash>/
```

The entire leaf directory is removed with `shutil.rmtree`.  The two
intermediate directories (`<AA>/` and `<AA>/<BB>/`) are also removed if they
become empty after deletion.

### 2. `pdf_catalog.db`

All rows keyed by `content_sha256`, deleted in FK-safe order:

- `metadata_resolved`
- `metadata_sources`
- `zotero_links`
- `source_sightings`
- `ingest_log`
- `canonical_files`

### 3. `rkb_documents.db` (project working database)

- `embeddings` for matching `doc_id`s
- `extractions` for matching `doc_id`s
- `documents` where `content_hash` matches

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success (PDF removed, or user aborted at prompt) |
| 1 | No match found, or multiple matches (ambiguous) |
| 130 | Interrupted (Ctrl-C or EOF at prompt) |
