---
name: kbase-research
description: Search the personal research-paper knowledge base (rkb MCP server) and read full papers efficiently. Use when the user asks about research literature, prior work, what papers say about a topic, or wants sources located in their PDF library.
---

# Searching the research knowledge base

The `rkb` MCP server indexes thousands of academic PDFs. Each paper has a
`doc_id` (SHA-256 of the PDF), a canonical directory containing the PDF and a
full Markdown extraction, and chunk-level search indexes.

## Workflow

1. **Search first.** Call `search_knowledge_base(query, mode, max_results)`.
   - `mode="hybrid"` is the right default (BM25 + semantic).
   - `mode="bm25"` for exact phrases, author names, or jargon.
   - `mode="semantic"` for conceptual queries with no distinctive keywords.
   - Run two or three differently-worded queries when recall matters; the
     union of results beats one query.

2. **Judge relevance from the hit itself.** Each hit includes `title`,
   `abstract`, and `best_chunk` (the passage that matched). Do not read a
   document until these suggest it is worth reading.

3. **Read promising papers via `markdown_path`, not chunk paging.** Each hit
   carries `markdown_path`, the full Markdown extraction on the local
   filesystem. When you have filesystem access (Claude Code), use the Read
   tool on `markdown_path` directly — one call for the whole paper, with
   intact equations and tables. Only page through the `read_document` MCP
   tool when you have no filesystem access.

4. **Navigate long papers with `search_within_document(doc_id, query,
   max_chunks)`** to find the relevant section before reading, instead of
   reading front to back.

5. **Cite with `pdf_link`.** Hits and chunks carry a `file://` URL to the
   source PDF, page-anchored (`#page=N`) when the page could be derived.
   When quoting or summarizing a specific claim, give the user the
   `pdf_link` so they can jump to the page and verify. Page anchors are
   approximate; omit the page claim if precision matters and verify against
   the PDF instead. Use `get_document(doc_id)` for authors, year, and
   journal when writing citations.

## Notes

- Figures and images referenced by the Markdown live in the same directory
  tree as `markdown_path`.
- If a hit has `markdown_path: null`, the paper has not been translated yet;
  tell the user to run `uv run rkb import` in the kbase repo.
- Chunk indexes run 0..chunk_cnt-1; `read_document` takes an inclusive range.
