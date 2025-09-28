# Projects

## What is a project?

A project in RKB is a logical grouping mechanism for organizing documents and their processing results. Projects are identified by a unique `project_id` string that follows the format `project_{timestamp}`. Documents can be associated with a project through the `project_id` field in the document model.

Projects provide organizational structure but do not create separate data silos. All documents across projects are stored in the same SQLite database, and the vector database stores embeddings from all projects together.

## How to use projects

### Creating a project

Create a new project using the CLI:

```bash
rkb project create "My Research Project" --description "Analysis of machine learning papers" --data-dir /path/to/pdfs
```

This generates a unique project ID and stores basic metadata. The project creation is lightweight - it only creates an identifier and prints confirmation.

### Listing projects

View all projects and their statistics:

```bash
rkb project list
```

This displays project IDs with document counts grouped by processing status (pending, extracted, indexed, failed).

### Viewing project details

Get detailed information about a specific project:

```bash
rkb project show project_1234567890
```

### Finding PDFs for a project

Discover PDF files and associate them with a project:

```bash
rkb project find-pdfs --data-dir /path/to/pdfs --project-id project_1234567890 --num-files 100
```

### Processing documents in a project

Process documents within a project context:

```bash
rkb pipeline --project-id project_1234567890 --data-dir /path/to/pdfs
```

Or for individual operations:

```bash
rkb extract --project-id project_1234567890 --data-dir /path/to/pdfs
rkb index --project-id project_1234567890
```

### Searching within a project

Limit search results to a specific project:

```bash
rkb search "machine learning" --project-id project_1234567890
```

### Creating document subsets

Create filtered views of documents within a project:

```bash
rkb project subset "recent_papers" --project-id project_1234567890 --status indexed --date-from 2024-01-01 --limit 50
```

### Exporting project data

Export project metadata and document information:

```bash
rkb project export project_1234567890 --output-file project_export.json
```

## When to use projects

### Recommended use cases

- **Research topics**: Group papers by research area or topic
- **Time periods**: Organize documents by acquisition date or research phase
- **Data sources**: Separate documents from different sources or repositories
- **Processing batches**: Track different batches of document processing
- **Experiments**: Isolate document sets for different experimental configurations

### Not recommended for

- **Access control**: Projects do not provide security isolation
- **Performance optimization**: All projects share the same databases
- **Version control**: Projects are not designed for document versioning

## Data storage implications

### Database schema

Projects affect data storage through the `project_id` field in the documents table:

```sql
CREATE TABLE documents (
    doc_id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    ...
    project_id TEXT,
    ...
);
```

An index is created on `project_id` for efficient filtering: `idx_documents_project`.

### Storage organization

- **Document registry**: All documents are stored in a single SQLite database (`rkb_documents.db` by default)
- **Vector database**: All embeddings are stored together in the same ChromaDB collection
- **Extraction files**: Extracted content files are not organized by project
- **Source files**: Projects do not move or reorganize source PDF files

### Data isolation

Projects provide logical separation but not physical isolation:

- Documents from different projects coexist in the same database tables
- Search can span multiple projects unless explicitly filtered
- Vector similarity search includes all projects by default
- Database backup and recovery affects all projects simultaneously

### Performance considerations

- Project filtering adds a WHERE clause to database queries
- Large numbers of projects do not significantly impact performance
- Project statistics require scanning all documents to compute counts
- No performance benefit from using multiple small projects versus one large project

### Data migration

Moving documents between projects requires updating the `project_id` field in the database. There is no built-in command for this operation.