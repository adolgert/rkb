# RKB Search — Guide for AI Agents

This document describes how an AI agent should interact with the RKB knowledge
base to retrieve information from a collection of scientific PDFs.

---

## Overview

The knowledge base indexes thousands of academic papers.  Each paper is split
into section-aware text chunks (~3000 characters).  Two parallel indexes exist:

- **Vector index** (SPECTER2, cosine similarity): good for conceptual
  similarity and paraphrase retrieval
- **BM25 keyword index**: good for exact terms — author names, equation
  symbols, dataset names, algorithm names

The `KnowledgeBase` Python API provides the recommended entry point.

---

## Instantiation

```python
from rkb.api import KnowledgeBase

kb = KnowledgeBase()
```

This is cheap.  The embedding model loads lazily on the first query.  Reuse
the same `kb` instance across multiple queries within a session.

---

## Primary method: `search()`

```python
hits: list[SearchHit] = kb.search(query, n=10, mode="hybrid")
```

### When to use each mode

| Situation | Recommended mode |
|-----------|-----------------|
| General topic exploration | `"hybrid"` (default) |
| Finding papers that discuss a concept without using those exact words | `"semantic"` |
| Looking up a specific author, algorithm name, dataset, or equation | `"bm25"` |
| Uncertain which is better | `"hybrid"` |

### `SearchHit` fields

```
hit.doc_id      — stable identifier; use this to fetch chunks or the file path
hit.score       — float, higher is more relevant; not comparable across modes
hit.title       — paper title (empty string if unknown)
hit.file_path   — Path to PDF/Markdown, or None
hit.best_chunk  — the most relevant passage for this query (~3000 chars max)
hit.section     — section heading of best_chunk, or None
```

---

## Retrieving passages from a known document

After identifying a relevant document, fetch its most relevant passages:

```python
passages: list[str] = kb.get_chunks(doc_id=hit.doc_id, query=query, n=5)
```

This is useful when `hit.best_chunk` is not enough context and you need to
read more of the paper.

---

## Typical agent patterns

### Pattern 1 — Find the most relevant papers on a topic

```python
hits = kb.search("stochastic simulation of chemical kinetics", n=5)
for h in hits:
    print(h.doc_id, h.title or h.file_path)
    print(h.best_chunk[:300])
```

### Pattern 2 — Find papers, then read deeply

```python
# Step 1: find candidate documents
hits = kb.search("tau-leaping approximation", n=3)

# Step 2: read the best passages from the top result
doc_id = hits[0].doc_id
passages = kb.get_chunks(doc_id, "tau-leaping approximation", n=5)

# Step 3: answer from the passages
context = "\n\n---\n\n".join(passages)
# ... pass context to LLM ...
```

### Pattern 3 — Search by exact term (author, algorithm, notation)

```python
# Author lookup
hits = kb.search("Gillespie 1977", mode="bm25", n=5)

# Equation symbol search (BM25 preserves LaTeX tokens)
hits = kb.search(r"\tau_leap convergence", mode="bm25")

# Algorithm name
hits = kb.search("next reaction method Gibson Bruck", mode="bm25")
```

### Pattern 4 — Cross-reference multiple queries

```python
queries = [
    "stochastic simulation algorithm",
    "chemical master equation",
    "Gillespie direct method",
]

# Collect unique papers mentioned across queries
seen = set()
results = []
for q in queries:
    for h in kb.search(q, n=5):
        if h.doc_id not in seen:
            seen.add(h.doc_id)
            results.append(h)
```

### Pattern 5 — Check whether the index is ready

```python
status = kb.index_status()
if not status["bm25_built"]:
    # BM25 not available; keyword queries will fall back gracefully
    pass
if status["total_chunks"] == 0:
    # Index is empty; no results will be returned
    pass
```

---

## What the index contains

- **Source**: academic PDFs extracted with marker-pdf or nougat
- **Chunk size**: up to 3000 characters, split at section boundaries
- **Section metadata**: each chunk carries its section heading (if the paper
  has headings), accessible via `hit.section` or in raw chunk metadata
- **Math**: LaTeX notation is preserved in chunk text and is BM25-searchable
  (e.g. `\lambda`, `x_i`, `A^n` are indexed as tokens)

---

## Limitations to be aware of

- `hit.score` values are **not comparable across sessions or modes**.  Use
  scores only for ranking within a single call.
- Papers with no section headings (older nougat extractions) fall back to
  page-based chunks; `hit.section` will be `None` for those.
- `hit.title` is empty when the paper was not enriched with metadata.  Use
  `hit.file_path.name` as a fallback label.
- If `kb.search()` returns fewer results than requested, the collection may
  not have documents matching that query — do not retry with identical queries.
- The BM25 index must be explicitly built (`rkb index --rebuild`) before
  `mode="bm25"` and `mode="hybrid"` return keyword-boosted results.  If the
  BM25 index is absent, hybrid mode silently degrades to semantic-only.

---

## Getting the source file

```python
path = kb.get_path(doc_id)
# path is a Path object pointing to the PDF, or None
```

This is useful when you need to tell the user where to find the paper, or
when you need to open it for page-level inspection.
