# PDF Collection Management Plan

## Mission

Build a quiet, dependable tool for managing a personal academic PDF collection
across work and home environments. The tool ensures every approved PDF ends up
in exactly two places at home: a canonical content-addressed store on Dropbox
(rock-solid backup) and in Zotero (with metadata, for research use).

This is infrastructure. It should be boring and correct. If it works, you
forget it exists and just have your papers where you need them.

## Why This Plan Exists

Previous work in this repository built extraction, embedding, and search
infrastructure for academic PDFs (the `rkb.extractors`, `rkb.embedders`,
`rkb.services`, and `rkb.pipelines` packages). That work remains valuable but
depends on a solved prerequisite: having a clean, deduplicated, trustworthy PDF
collection. This plan focuses exclusively on that prerequisite.

The owner has 2000+ existing PDFs scattered across Dropbox/Mendeley, Zotero
storage, and other locations. New PDFs arrive at roughly 10/week, some from a
work machine that requires manual review before transfer home. The goal is to
impose order on this collection and keep it ordered going forward.

The separate `findpdfs` package in this repository contains useful exploratory
code (PDF hashing, duplicate detection, BibTeX parsing, LLM-based
classification) that will be adapted into the new system. `findpdfs` is treated
as a parts bin, not a running system.

## Environments

| Environment   | OS           | Role                                     |
|---------------|--------------|------------------------------------------|
| Work laptop   | MacOS        | PDF triage: review, approve/reject, stage for Box upload |
| Home desktop  | Pop!_OS      | Primary: canonical storage, Zotero, ingest |
| Home laptop   | MacOS        | Secondary: same capabilities as home desktop |

Box serves as a dumb transport bridge between work and home. No application
logic runs on Box. The tool does not integrate with the Box API; the user
uploads and downloads manually.

## Core Invariants

1. **Every PDF is identified by SHA-256 of its bytes.** No other hash is used
   for identity or deduplication decisions. (SHA-1 exists in legacy `findpdfs`
   code and will not be carried forward.)

2. **The canonical store on Dropbox is the source of truth for PDF bytes.** If
   any other copy (Zotero, work machine, old Mendeley folder) is lost or
   corrupted, the canonical store can restore it.

3. **Zotero is a reading/metadata copy, not authority.** If Zotero loses a
   file, we re-provide it from the canonical store. If Zotero has metadata we
   lack, we may read it, but Zotero never determines what PDFs we have.

4. **All commands are idempotent.** Running any command twice produces the same
   end state as running it once. This is the most important property for a tool
   you run without thinking.

5. **Triage decisions are mutable.** Any thumbs-up can become a thumbs-down and
   vice versa. The staging directory always reflects current decisions. If you
   can go forward, you can go backward.

6. **Source files are never modified or deleted by the tool.** It only copies.
   Cleaning up source directories is the user's responsibility.

## Architecture

```
WORK MACHINE                          HOME MACHINE
+-------------------+                +-----------------------------+
|  ~/Downloads/     |                |  ~/Dropbox/                 |
|    (PDFs land)    |                |    findpdfs-library/        |
|        |          |                |      sha256/ab/cd/          |
|        v          |                |        <hash>/              |
|  rkb triage       |                |          author title.pdf   |
|  (Flask web app)  |                |                             |
|        |          |                |  ~/Zotero/storage/          |
|  approve/reject   |                |    (Zotero's own copy)      |
|        |          |                |                             |
|        v          |                |  ~/Documents/               |
|  ~/Documents/     |   --Box-->     |    box-staging/             |
|    box-staging/   |                |    (inbox from work)        |
|                   |                |        |                    |
|  triage.db        |                |        v                   |
|  (decisions)      |                |  rkb ingest                 |
+-------------------+                |  (CLI tool)                 |
                                     |        |                    |
                                     |   +----+----+               |
                                     |   v         v               |
                                     | Dropbox   Zotero            |
                                     | store     import            |
                                     |                             |
                                     |  pdf_catalog.db             |
                                     +-----------------------------+
```

## What Is In Scope

- Content-addressed PDF storage on Dropbox with human-readable filenames
- Work-side PDF triage with mutable, reversible decisions
- Home-side ingest from any inbox directory
- Zotero integration: import PDFs, detect duplicates by hash, avoid creating
  duplicate Zotero entries
- One-time rectification of existing collections (Mendeley, Zotero, other dirs)
- Status reporting

## What Is Out of Scope (For Now)

- PDF-to-Markdown conversion (may use purchased/downloaded software later)
- Text chunking, embedding, vector search
- LLM/AI interaction layer (will build on top of the collection later)
- Box API integration (manual upload/download for now)
- Programmatic metadata retrieval beyond what Zotero provides built-in

## Technology Choices

| Choice | Rationale |
|--------|-----------|
| Python, in the `rkb` package | Existing codebase with clean architecture, shared hashing/identity code, import-linter enforcement |
| SHA-256 for identity | Already used in rkb core; stronger than SHA-1 in findpdfs; widely standard |
| SQLite (fresh `pdf_catalog.db`) | Simple, portable, inspectable with standard tools. Fresh DB avoids inheriting legacy schema from `rkb_documents.db` |
| Flask for triage web UI | Lightweight, Python-native, renders in any browser, no native GUI dependencies. Works identically on MacOS |
| PyMuPDF for PDF rendering | Fast page-to-image conversion for the triage UI. Works on MacOS and Linux. Already an optional rkb dependency |
| pyzotero for Zotero API | Already a dependency in findpdfs, well-maintained, handles item creation and file attachment via Zotero Web API |
| Content-addressed store with human-readable names | Hash directories guarantee dedup; human-readable filenames provide disaster recovery if the database is ever lost |

## Existing Code to Reuse

Code from `findpdfs` and `rkb` will be adapted (not imported directly) into the
new `rkb.collection` subpackage:

| Source | What it does | Use in new system |
|--------|-------------|-------------------|
| `rkb/core/identity.py` | SHA-256 hashing, source type detection | Adapt hashing function |
| `findpdfs/identify.py` | PDF metadata extraction, page count, text length, SSN/name detection | Display name generation; triage info display |
| `findpdfs/exactmatch.py` | Hash-based destination paths, duplicate detection | Canonical store path layout |
| `findpdfs/store.py` | Hash-to-traits storage pattern | Reference for catalog design |
| `findpdfs/bibtex.py` | BibTeX parsing, title-based dedup, Mendeley/Zotero export handling | Rectification: matching PDFs to existing metadata |
| `findpdfs/gather.py` | First-page text extraction, LLM paper classification | Triage: display info, optional "is this science?" filter |

## Document Index

This plan is organized into the following documents:

| Document | Purpose |
|----------|---------|
| [OVERVIEW.md](OVERVIEW.md) | This file. Goals, rationale, architecture |
| [DATA_MODEL.md](DATA_MODEL.md) | Database schemas, canonical store layout, configuration |
| [CORE_LIBRARY.md](CORE_LIBRARY.md) | Shared library modules (hashing, catalog, paths, config) |
| [HOME_INGEST.md](HOME_INGEST.md) | `rkb ingest` command specification |
| [WORK_TRIAGE.md](WORK_TRIAGE.md) | `rkb triage` web application specification |
| [ZOTERO_INTEGRATION.md](ZOTERO_INTEGRATION.md) | Zotero sync: hash scanning, import, dedup |
| [RECTIFY.md](RECTIFY.md) | One-time rectification of existing collections |
| [IMPLEMENTATION_PHASES.md](IMPLEMENTATION_PHASES.md) | Build order, parallelization, verification criteria |
