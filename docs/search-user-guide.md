# RKB Search — User Guide

This guide covers every way to search your document collection from the command
line.  There are two commands: `rkb search` (chunk-level results) and
`rkb documents` (document-level results).  Both support three search modes.

---

## Search modes

| Mode | What it does |
|------|-------------|
| `hybrid` | Combines keyword (BM25) and semantic results with Reciprocal Rank Fusion.  **Default.** Best general-purpose choice. |
| `semantic` | Pure vector similarity.  Finds conceptually related text even when the exact words differ. |
| `bm25` | Pure keyword search.  Best for author names, equation symbols, dataset names, and other exact tokens. |

---

## Building the index

Before searching, documents must be indexed.  The recommended approach uses
SPECTER2 (a model trained on scientific papers) and builds both the vector
index and the BM25 keyword index in one step.

```bash
# Index all extracted documents with SPECTER2 (first time)
rkb index --embedder specter2

# Wipe the old index and rebuild from scratch
rkb index --embedder specter2 --rebuild
```

`--rebuild` is required when you want to start fresh — it guards against
accidentally wiping data.

Other embedder options if SPECTER2 is unavailable:

```bash
rkb index --embedder chroma    # Chroma's built-in MiniLM model
rkb index --embedder ollama    # Local Ollama model
```

---

## `rkb documents` — find relevant *papers*

Returns a ranked list of documents (papers) with a preview of the best
matching passage.

### Basic hybrid search (default)

```bash
rkb documents "stochastic simulation stability"
```

### Choose the search mode

```bash
rkb documents "eigenvalue bounds random matrices" --mode bm25
rkb documents "Markov chain Monte Carlo" --mode semantic
rkb documents "Gillespie algorithm convergence" --mode hybrid
```

### Tune the result count

```bash
rkb documents "importance sampling" -n 20
```

### Choose how documents are ranked

The `--metric` option applies only in `--mode semantic` and controls how
chunk-level scores are combined into a document score.

```bash
# similarity: document score = score of its best-matching chunk
rkb documents "Lyapunov stability" --mode semantic --metric similarity

# relevance: document score = count of chunks above the threshold
rkb documents "Lyapunov stability" --mode semantic --metric relevance
```

### Filter by equations

```bash
rkb documents "convergence proof" --filter-equations   # only papers with math
rkb documents "benchmark comparison" --no-equations    # only text-heavy papers
```

### Filter by project

```bash
rkb documents "diffusion" --project-id my_project
```

### Show database statistics

```bash
rkb documents --stats
```

### Interactive mode

```bash
rkb documents          # starts interactive loop
rkb documents -i       # same
```

In interactive mode type a query and press Enter.  Type `stats` for database
info, `help` for commands, or `exit` to quit.

---

## `rkb search` — find relevant *passages*

Returns individual text chunks rather than whole documents.  Useful when you
want to read the exact passage that matched.

```bash
rkb search "chemical Langevin equation"

# With mode
rkb search "noise-induced transitions" --mode bm25

# Limit results
rkb search "mean first passage time" -n 10

# Filter to equation-heavy chunks
rkb search "Fokker-Planck" --filter-equations

# Within specific documents
rkb search "boundary condition" --document-ids doc_abc doc_xyz

# Show database stats
rkb search --stats
```

---

## Understanding the output

`rkb documents` output looks like this:

```
📊 Found 5 documents for: 'stochastic simulation stability'
📈 Metric: relevance | Fetched 412 chunks in 1 iteration(s)
================================================================================

🔖 Result 1
   Relevance: 7 hits | Similarity: 0.823
📄 Document: gillespie_1977.pdf
🔗 Link: file:///path/to/gillespie_1977.pdf#page=3
📝 Extraction: rkb_extractions/abc123.mmd
📝 Preview:
   The direct method produces sample paths...
```

- **Relevance hits**: number of chunks above the similarity threshold
- **Similarity**: score of the single best-matching chunk
- **Link**: opens the PDF at the relevant page in your PDF viewer
- **Extraction**: the Markdown extraction file (useful for copy-pasting math)

---

## Common workflows

### Find a paper you remember partially

```bash
# You remember it was about "tau-leaping" and had "Cao" as an author
rkb documents "Cao tau-leaping" --mode bm25
```

### Explore a topic you don't know well

```bash
# Semantic is better when you're searching by concept, not exact terms
rkb documents "approximation of chemical reaction networks" --mode semantic
```

### Find papers with specific notation

```bash
# BM25 matches LaTeX tokens like \lambda, x_i, etc.
rkb search '\lambda convergence rate' --mode bm25
```

### Compare a document to the rest of the collection

```bash
# Find papers similar to a specific chunk (from a previous search result)
# chunk IDs are shown with rkb search output
rkb search "copy the text of the passage here"
```
