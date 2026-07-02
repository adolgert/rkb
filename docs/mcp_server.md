# RKB MCP Server

The RKB knowledge base exposes four tools via the [Model Context Protocol](https://modelcontextprotocol.io/) (MCP), allowing AI assistants to search and read documents without any manual copy-paste. The server runs locally as a stdio process started on demand by the client.

The server entry point is `rkb/mcp_server.py`. It loads the same indexes as the CLI and responds to tool calls over stdin/stdout.

---

## Tools

### `search_knowledge_base`

Find documents that match a query.

| Parameter | Type | Description |
|-----------|------|-------------|
| `query` | string | Natural language question or keyword phrase |
| `mode` | string | `"hybrid"` (default), `"semantic"`, or `"bm25"` |
| `max_results` | integer | Maximum number of documents to return |

Returns a list of **SearchHit** objects, sorted by relevance (highest first):

| Field | Type | Description |
|-------|------|-------------|
| `doc_id` | string | SHA-256 hash identifying the document |
| `score` | float | Relevance score; higher is better |
| `title` | string | Paper title, or filename if title is unknown |
| `dir_path` | string | Absolute path to the document's directory (contains the PDF, Markdown, and extracted images) |
| `chunk_cnt` | int \| null | Number of indexed Markdown chunks |
| `page_cnt` | int \| null | Number of PDF pages; null if unavailable |
| `abstract` | string | Abstract text; empty string if not extracted |
| `best_chunk` | string | Text of the chunk that best matched the query — judge relevance from this before reading the document |
| `section` | string \| null | Section heading of `best_chunk`, when known |
| `markdown_path` | string \| null | Path to the full Markdown extraction. Clients with filesystem access should read this file directly instead of paging through `read_document`. Null if the document has not been translated |
| `pdf_link` | string \| null | `file://` URL of the source PDF, anchored (`#page=N`) to the approximate page of `best_chunk` when derivable |

Search modes:

- **hybrid** — combines BM25 keyword matching and SPECTER2 vector similarity via Reciprocal Rank Fusion. Best for most queries.
- **semantic** — vector similarity only. Better for conceptual questions with no exact keywords.
- **bm25** — keyword matching only. Better for author names, acronyms, or exact phrases.

---

### `read_document`

Read a contiguous range of Markdown chunks from a document.

| Parameter | Type | Description |
|-----------|------|-------------|
| `doc_id` | string | SHA-256 document identifier |
| `chunk_start` | integer | 0-based index of the first chunk to return |
| `chunk_finish` | integer | 0-based index of the last chunk to return (inclusive) |

Returns a list of **Chunk** objects in index order:

| Field | Type | Description |
|-------|------|-------------|
| `doc_id` | string | SHA-256 document identifier |
| `chunk_idx` | integer | Position of this chunk within the document |
| `chunk_cnt` | integer | Total number of chunks in the document |
| `content` | string | Markdown text of the chunk |
| `similarity` | null | Always null for sequential reads |
| `pdf_link` | string \| null | `file://` URL of the source PDF, anchored (`#page=N`) to the approximate page the chunk starts on when derivable — use it to cite quotes |

Use `chunk_cnt` from a prior `search_knowledge_base` or `get_document` call to know the valid index range (0 to `chunk_cnt - 1`). Fetch chunks in pages; a reasonable page size is 5–10 chunks.

---

### `search_within_document`

Find the most relevant sections of a single document for a query.

| Parameter | Type | Description |
|-----------|------|-------------|
| `doc_id` | string | SHA-256 document identifier |
| `query` | string | Natural language query |
| `max_chunks` | integer | Maximum number of chunks to return |

Returns a list of **Chunk** objects ranked by relevance. The `similarity` field (0–1) is populated for each chunk.

Useful when a document is long and you want to skip to the relevant section rather than reading it sequentially.

---

### `get_document`

Look up full metadata for a document by its identifier.

| Parameter | Type | Description |
|-----------|------|-------------|
| `doc_id` | string | SHA-256 document identifier |

Returns a **DocumentInfo** object:

| Field | Type | Description |
|-------|------|-------------|
| `doc_id` | string | SHA-256 document identifier |
| `title` | string | Paper title; empty string if unknown |
| `authors` | list[string] | Author names; empty list if unknown |
| `year` | int \| null | Publication year |
| `journal` | string \| null | Journal or venue name |
| `abstract` | string | Abstract text; empty string if not extracted |
| `page_cnt` | int \| null | Number of PDF pages |
| `chunk_cnt` | integer | Number of indexed Markdown chunks |
| `dir_path` | string | Absolute path to the document's directory |
| `markdown_path` | string \| null | Path to the full Markdown extraction; null if not translated |
| `pdf_link` | string \| null | `file://` URL of the source PDF |

Page anchors in `pdf_link` are recovered from artifacts marker-pdf leaves in the Markdown (image filenames and span anchors), so they are approximate and absent for passages without such artifacts.

---

## Installing in Claude Desktop

Claude Desktop reads `claude_desktop_config.json` at startup. Edit it to add the server.

**Config file locations:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

> **Linux note:** Anthropic does not publish an official Claude Desktop package for Linux. Community-maintained builds exist for [Debian/Ubuntu](https://github.com/aaddrick/claude-desktop-debian) and [Arch Linux](https://github.com/aaddrick/claude-desktop-arch), and a Snap package is available via the [Snap Store](https://snapcraft.io/claudeai-desktop). All of them use the XDG config path above. Claude Code (the terminal tool) is the officially supported Anthropic client on Linux and is the better choice if you have not already committed to a specific community build.

Add an `mcpServers` entry (adjust the path to match your checkout):

```json
{
  "mcpServers": {
    "rkb": {
      "command": "uv",
      "args": [
        "run",
        "--project", "/home/you/dev/kbase",
        "python", "/home/you/dev/kbase/rkb/mcp_server.py"
      ]
    }
  }
}
```

Restart Claude Desktop after saving the file. The RKB tools appear in the tool list automatically.

**To uninstall:** Remove the `"rkb"` block from `mcpServers` and restart Claude Desktop.

---

## Installing in Claude Code (CLI)

Run this command from any directory:

```bash
claude mcp add --scope user --transport stdio rkb -- \
  uv run --project /home/you/dev/kbase \
  python /home/you/dev/kbase/rkb/mcp_server.py
```

- `--scope user` makes it available in all projects. Use `--scope project` to restrict it to the current project (writes to `.mcp.json` in the project root).
- `--transport stdio` is correct for this server.

Verify it registered:

```bash
claude mcp list
```

**To uninstall:**

```bash
claude mcp remove rkb
```

---

## Installing in Gemini CLI

Gemini CLI reads MCP configuration from `settings.json`.

**Config file locations:**
- User-level (all projects): `~/.gemini/settings.json`
- Project-level: `.gemini/settings.json` in the project directory

Add an `mcpServers` entry:

```json
{
  "mcpServers": {
    "rkb": {
      "command": "uv",
      "args": [
        "run",
        "--project", "/home/you/dev/kbase",
        "python", "/home/you/dev/kbase/rkb/mcp_server.py"
      ]
    }
  }
}
```

Or use the CLI helper:

```bash
gemini mcp add rkb uv run --project /home/you/dev/kbase python /home/you/dev/kbase/rkb/mcp_server.py
```

**To uninstall:** Remove the `"rkb"` block from `mcpServers` in `settings.json`, or run:

```bash
gemini mcp remove rkb
```

---

## Installing in Codex

Codex reads MCP configuration from `config.toml`.

**Config file locations:**
- Global: `~/.codex/config.toml`
- Project-scoped (trusted projects only): `.codex/config.toml`

Add a server block:

```toml
[mcp_servers.rkb]
command = "uv"
args = [
  "run",
  "--project", "/home/you/dev/kbase",
  "python", "/home/you/dev/kbase/rkb/mcp_server.py"
]
```

The configuration is shared between the Codex CLI and its IDE extension automatically.

**To uninstall:** Delete the `[mcp_servers.rkb]` block from `config.toml`.

---

## Running the server directly

For debugging or testing outside of a client:

```bash
# Start the server (exits immediately without a client connected)
uv run python rkb/mcp_server.py

# Interactive testing with fastmcp dev mode
fastmcp dev rkb/mcp_server.py
```

`fastmcp dev` opens a browser-based inspector where you can call tools manually and inspect responses.
