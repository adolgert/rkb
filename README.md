# Research Knowledge Base (RKB)

A personal knowledge base for thousands of academic PDFs. Papers live in a
content-addressed canonical store (`~/Dropbox/findpdfs-library`), get their
bibliographic metadata resolved automatically, are translated to Markdown with
OCR, and are indexed for hybrid semantic + keyword search. The results are
readable three ways: through an MCP server (for AI assistants), from the
command line, and mirrored into Zotero for visual browsing and cross-machine
sync.

This catalog — not Zotero, not any one folder — is the definitive record of
which papers exist. Every document is identified by the SHA-256 of its PDF
content, so the same paper saved in five places imports exactly once.

## Setup

```bash
uv sync

# API keys live in local.env (gitignored). Required keys:
#   GEMINI_API_KEY       marker-pdf translation + last-resort metadata reading
#   ANTHROPIC_API_KEY    metadata merging (Claude)
#   S2_API_KEY           Semantic Scholar lookups
#   ZOTERO_LIBRARY_ID    Zotero mirror (zotero-push)
#   ZOTERO_API_KEY       Zotero mirror (zotero-push)
set -a && source local.env && set +a

# Two local services support metadata resolution:
docker compose up -d     # grobid + zotero translation-server
```

Note on the translation-server image: Docker Hub's images are unusable on
x86_64 (`latest` is arm64-only; the newest amd64 tag is too old for current
translators). Build it locally — instructions are in `docker-compose.yml`.

All commands run via `uv run` (bare `rkb` will miss dependencies). Progress
bars go to stderr; append `2>/dev/null` when you want quiet output.

## The main flow: importing new papers

1. **Gather** PDFs into `~/Downloads` on any machine (home laptop, work
   laptop, desktop).
2. **Triage** what is worth keeping: `uv run rkb triage` opens a local web app
   that reviews the downloads and stages approved files.
3. **Move** the keepers into `~/Dropbox/Mendeley` (any subdirectory; a dated
   folder like `imports/20260629` works well). Dropbox syncs them to the
   desktop.
4. **Import** on the desktop:

   ```bash
   uv run rkb import
   ```

   This single command runs the whole pipeline against `~/Dropbox/Mendeley`
   (recursively): ingest new PDFs into the canonical store, resolve metadata
   and rename, translate to Markdown, and index for search. It loads API keys
   from `local.env` automatically, prints a per-step summary, and is safe to
   re-run at any time — every step skips work already done.

   Useful variants:
   - `uv run rkb import --dry-run` — preview all three steps.
   - `uv run rkb import ~/some/other/dir` — import from a different directory.

5. **Verify**: `uv run rkb recent` lists the newest imports with clickable
   `file://` links to each PDF and the path to its Markdown.

6. **Mirror to Zotero** (optional, for visual browsing and cloud sync):

   ```bash
   uv run rkb zotero-push -n 500
   ```

   Pushes proper bibliographic items (title, authors, year, venue) with the
   PDF attached as a child, newest first, up to the limit per run. Only
   documents with a resolved title are pushed. Re-run until caught up — the
   catalog ledger tracks what has been pushed, so every run resumes where the
   last stopped.

Reading "Duplicate" in the ingest summary: it means *that file's content is
already in the library* — either imported previously or saved in more than one
place. It is the normal, boring answer, not an error.

## Reading and searching

- **MCP server** — the primary way to search from an AI assistant. Exposes
  `search_knowledge_base`, `read_document`, `search_within_document`, and
  `get_document`. Search hits include the best-matching passage, the path to
  the full Markdown (read it directly instead of paging chunks), and
  page-anchored `file://` links for citation. Setup and tool reference:
  [docs/mcp_server.md](docs/mcp_server.md). A portable agent skill encoding
  the recommended workflow is in
  [docs/skills/kbase-research/](docs/skills/kbase-research/SKILL.md).
- **Command line**:
  - `uv run rkb documents "query"` — document-level search with `file://`
    links.
  - `uv run rkb search "query"` — chunk-level search.
  - `uv run rkb recent -n 20` — newest imports.
  - `uv run rkb status` — collection counts and recent activity.
  - `uv run rkb topics` — BERTopic clustering across the corpus.

## The flow, step by step

`rkb import` is a wrapper around three commands you can also run individually:

| Step | Command | What it does |
|---|---|---|
| 1 | `uv run rkb ingest --resolve <DIR>` | Hash each PDF, copy new ones into `<library>/sha256/ab/cd/<hash>/`, record them in the catalog (`pdf_catalog.db`), then resolve metadata and rename to `Author Year Title.pdf` |
| 2 | `uv run rkb translate` | Convert every canonical PDF without an extraction to Markdown (marker-pdf + Gemini). The slow step: plan hours for a large backlog |
| 3 | `uv run rkb index` | Chunk the Markdown, embed with SPECTER2, build the Chroma vector index and the BM25 keyword index |

Metadata resolution consults, in priority order: the Zotero translation-server
(DOI/arXiv lookups, registrar quality), GROBID, Semantic Scholar, CrossRef,
arXiv, embedded XMP, then two fallbacks for documents with no identifiers — a
title search seeded from the Markdown's first heading (accepted only when an
author on the title page corroborates the match), and finally Gemini Flash
reading the title page like a human would (accepted only when the title it
returns actually appears in the text). Results from multiple sources are
merged by Claude.

## When something fails

**Translation aborts mid-run (Gemini outage or bad key).** The run stops
rather than corrupting output; nothing is marked failed. Fix the key or wait
out the outage, then re-run `uv run rkb translate` (or `rkb import`) — it
picks up exactly where it left off.

**Documents imported but metadata is missing.** Run `uv run rkb enrich` (with
`local.env` sourced). It re-attempts every document that has no resolved
metadata — "nothing found" results are never cached, so each enrich run
retries them with the current extractor stack. The summary distinguishes
`Metadata found` from `Nothing found`; documents that stay in "nothing found"
are genuinely signal-free scans. To re-resolve documents that already have
(possibly poor) metadata, use `rkb enrich --force`.

**Metadata quality is poor and grobid/translation-server were down.** Check
`docker ps`, then `docker compose up -d`, then `rkb enrich` — resolution
degrades gracefully when the containers are missing, but the results are
weaker.

**A document has Markdown but doesn't show up in search.** Run
`uv run rkb index` — it indexes anything translated but not yet indexed. For
a document that indexed badly, `--force-reindex` re-embeds everything;
`--rebuild` wipes the Chroma collection and BM25 index and starts clean.

**`zotero-push` was interrupted or rate-limited.** Just re-run it. Selection
is ledger-driven (`zotero_links` in the catalog): pushed documents are never
re-pushed, failed ones are retried, and a persistent rate limit aborts the run
cleanly leaving the remainder for next time.

**A wrong or unwanted PDF got imported.** `uv run rkb remove <title fragment
or sha256>` deletes the PDF, its extractions, and all its catalog and index
records.

**PDFs are scattered across old locations (Zotero storage, loose folders).**
`uv run rkb rectify --scan <dirs...>` is the one-time reconciliation that
sweeps stragglers into the canonical store. Rarely needed now.

## Data layout

```
~/Dropbox/findpdfs-library/
├── db/pdf_catalog.db          # the catalog: files, metadata, provenance, Zotero ledger
└── sha256/
    ├── ab/cd/<full-hash>/     # one directory per document
    │   ├── Author Year Title.pdf
    │   ├── metadata.bib
    │   └── extractions/marker-pdf-<version>/extracted.md (+ images)
    ├── rkb_chroma_db/         # vector index
    ├── rkb_chunks.db          # chunk text
    └── rkb_documents.db       # search-side document registry
```

Configuration precedence: defaults < YAML (`<library>/config.yaml` or
`~/.config/rkb/collection.yaml`) < environment (`PDF_LIBRARY_ROOT`,
`PDF_CATALOG_DB`, `ZOTERO_*`, ...). See `rkb/collection/config.py`.

## Development

```bash
uv run pytest          # all tests (unit tests scrub API keys; no network)
uv run ruff check rkb tests
uv run lint-imports    # layer architecture: cli|mcp > api > services > pipelines > extractors|embedders|collection > core
```

## Retired functionality

The `project` and `experiment` command groups (grouping documents into
projects, comparing embedders) are no longer wired into the CLI, and the
nougat-era `pipeline`/`extract`/`find` commands are deprecated. Their modules
and some database columns (`project_id`) remain, but nothing uses them.
`docs/projects.md` and `docs/CLI_TUTORIAL.md` describe that retired system and
are kept for historical reference only.
