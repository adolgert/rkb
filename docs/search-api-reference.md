# RKB Search — Python API Reference

The `rkb.api` module provides a stable, high-level Python interface to the
knowledge base.  It wraps `SearchService`, `BM25Index`, and `DocumentRegistry`
so callers do not have to manage individual services.

---

## Quick start

```python
from rkb.api import KnowledgeBase

kb = KnowledgeBase()          # defaults: specter2 embedder, rkb_chroma_db/
hits = kb.search("stochastic simulation stability", n=5)

for h in hits:
    print(h.score, h.title)
    print(h.best_chunk[:200])
    print(h.file_path)
```

---

## `KnowledgeBase`

```python
class KnowledgeBase:
    def __init__(
        self,
        db_path: Path | str | None = None,   # default: "rkb_chroma_db"
        embedder: str = "specter2",           # "specter2" | "chroma" | "ollama"
        registry_path: Path | str | None = None,  # default: "rkb_documents.db"
    ) -> None
```

Instantiating `KnowledgeBase` automatically loads the BM25 index from disk if
it exists.  Construction is cheap — the embedding model is loaded lazily on
the first query.

---

### `search()`

```python
def search(
    self,
    query: str,
    n: int = 10,
    mode: str = "hybrid",   # "hybrid" | "semantic" | "bm25"
) -> list[SearchHit]
```

Returns at most `n` document-level results sorted by score descending.

**Modes:**

| `mode` | Description |
|--------|-------------|
| `"hybrid"` | BM25 + semantic combined via Reciprocal Rank Fusion (k=60). Recommended default. |
| `"semantic"` | Vector similarity only (SPECTER2 or configured embedder). |
| `"bm25"` | Keyword search only. Good for author names, equation tokens, dataset identifiers. |

**Example:**

```python
hits = kb.search("eigenvalue perturbation theory", n=10, mode="hybrid")
hits = kb.search("\\lambda_max bounds", mode="bm25")   # LaTeX token search
hits = kb.search("concentration inequalities", mode="semantic")
```

---

### `get_chunks()`

```python
def get_chunks(
    self,
    doc_id: str,
    query: str,
    n: int = 5,
) -> list[str]
```

Returns the top `n` text chunks from `doc_id` most relevant to `query`.
Useful for reading the actual passages after a document-level search.

**Example:**

```python
hits = kb.search("Gillespie algorithm")
top_doc = hits[0].doc_id

# Read the 3 most relevant passages from that paper
passages = kb.get_chunks(top_doc, "Gillespie algorithm", n=3)
for p in passages:
    print(p)
    print("---")
```

---

### `get_path()`

```python
def get_path(self, doc_id: str) -> Path | None
```

Returns the path to the source PDF/Markdown file for `doc_id`, or `None` if
the document is not in the registry.

---

### `index_status()`

```python
def index_status(self) -> dict[str, object]
```

Returns a summary of the current index state.

```python
status = kb.index_status()
# {
#   "total_chunks": 48231,
#   "bm25_built": True,
#   "embedder": "specter2",
# }
```

---

## `SearchHit`

```python
@dataclass
class SearchHit:
    doc_id: str           # unique document identifier
    score: float          # retrieval score (higher = more relevant)
    title: str            # document title from registry ("" if unknown)
    file_path: Path | None  # path to source PDF/Markdown
    best_chunk: str       # text of the highest-scoring passage for this query
    section: str | None   # section heading of best_chunk (None if unavailable)
```

---

## Lower-level access

For operations not exposed by `KnowledgeBase`, use the underlying services
directly.

### `SearchService`

```python
from rkb.services.search_service import SearchService
from rkb.services.bm25_index import BM25Index

bm25 = BM25Index("rkb_chroma_db")
bm25.load()

svc = SearchService(
    db_path="rkb_chroma_db",
    embedder_name="specter2",
    bm25_index=bm25,
)

# Document-level search
ranked_docs, all_chunks, stats = svc.search_documents_ranked(
    query="stochastic simulation",
    n_docs=10,
    mode="hybrid",       # "hybrid" | "semantic" | "bm25"
    metric="similarity", # used only when mode="semantic"
    min_threshold=None,  # None = use embedder default
)

# Chunk-level search (returns raw passages)
result = svc.search_documents("Lyapunov function", n_results=20)
for chunk in result.chunk_results:
    print(chunk.similarity, chunk.content[:100])

# Search within a specific document
result = svc.search_by_document("my query", doc_id="abc123", n_results=5)

# Display data for a ranked document
display = svc.get_display_data(ranked_docs[0], all_chunks)
# {"chunk_text": "...", "chunk_score": 0.82, "page_numbers": [3], "chunk_id": "..."}
```

### `BM25Index`

```python
from rkb.services.bm25_index import BM25Index
from pathlib import Path

idx = BM25Index(Path("rkb_chroma_db"))

# Build from (chunk_id, text) pairs
idx.build([("doc1_chunk0", "text content..."), ...])

# Load from disk
ok = idx.load()  # returns False if files don't exist

# Search: returns (chunk_id, normalised_score) pairs, score in [0, 1]
results = idx.search("Gillespie tau-leaping", n=100)

# Wipe files and reset
idx.wipe()
```

### Section-aware chunking

```python
from rkb.core.text_processing import chunk_text_by_sections

# Returns list of (chunk_text, section_hierarchy) tuples
chunks = chunk_text_by_sections(markdown_text, max_chunk_size=3000)

for text, hierarchy in chunks:
    section = hierarchy[0] if hierarchy else "(preamble)"
    print(f"[{section}] {text[:80]}")
```

---

## Embedder note

The `specter2` embedder lazy-loads `allenai/specter2_base` via
`sentence-transformers` on first use.  This triggers a one-time model download
(~440 MB).  Subsequent instantiations reuse the cached model.  No GPU is
required.

To verify the model loads correctly:

```python
from rkb.embedders.specter2_embedder import Specter2Embedder

e = Specter2Embedder()
vec = e.embed_query("test")
print(len(vec))  # 768
```
