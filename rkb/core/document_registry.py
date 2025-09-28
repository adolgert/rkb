"""Document registry for tracking processed documents with SQLite backend."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from rkb.core.models import Document, DocumentStatus, ExtractionResult, EmbeddingResult


class DocumentRegistry:
    """SQLite-based registry for tracking documents and their processing status."""

    def __init__(self, db_path: Path | str = "rkb_documents.db"):
        """Initialize document registry.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._init_database()

    def _init_database(self) -> None:
        """Initialize the SQLite database with required tables."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    doc_id TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL,
                    content_hash TEXT,
                    title TEXT,
                    authors TEXT,  -- JSON array as text
                    arxiv_id TEXT,
                    doi TEXT,
                    version INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'pending',
                    added_date TEXT NOT NULL,
                    updated_date TEXT NOT NULL,
                    project_id TEXT,
                    UNIQUE(source_path)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS extractions (
                    extraction_id TEXT PRIMARY KEY,
                    doc_id TEXT NOT NULL,
                    extractor_name TEXT NOT NULL,
                    extractor_version TEXT NOT NULL,
                    extraction_path TEXT,
                    content TEXT,
                    page_count INTEGER,
                    status TEXT DEFAULT 'complete',
                    error_message TEXT,
                    extraction_date TEXT NOT NULL,
                    FOREIGN KEY (doc_id) REFERENCES documents (doc_id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS embeddings (
                    embedding_id TEXT PRIMARY KEY,
                    doc_id TEXT,
                    extraction_id TEXT,
                    embedder_name TEXT NOT NULL,
                    embedder_version TEXT NOT NULL,
                    vector_db_path TEXT,
                    chunk_count INTEGER DEFAULT 0,
                    embedding_date TEXT NOT NULL,
                    error_message TEXT,
                    FOREIGN KEY (doc_id) REFERENCES documents (doc_id),
                    FOREIGN KEY (extraction_id) REFERENCES extractions (extraction_id)
                )
            """)

            # Create indexes for better performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_project ON documents (project_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_status ON documents (status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_extractions_doc ON extractions (doc_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_doc ON embeddings (doc_id)")

    def add_document(self, document: Document) -> bool:
        """Add a document to the registry.

        Args:
            document: Document to add

        Returns:
            True if added successfully, False if already exists
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO documents (
                        doc_id, source_path, content_hash, title, authors,
                        arxiv_id, doi, version, status, added_date, updated_date, project_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    document.doc_id,
                    str(document.source_path) if document.source_path else None,
                    document.content_hash,
                    document.title,
                    ",".join(document.authors) if document.authors else None,
                    document.arxiv_id,
                    document.doi,
                    document.version,
                    document.status.value,
                    document.added_date.isoformat(),
                    datetime.now().isoformat(),
                    getattr(document, 'project_id', None),
                ))
                return True
        except sqlite3.IntegrityError:
            return False  # Document already exists

    def get_document(self, doc_id: str) -> Document | None:
        """Get a document by ID.

        Args:
            doc_id: Document identifier

        Returns:
            Document if found, None otherwise
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM documents WHERE doc_id = ?
            """, (doc_id,))
            row = cursor.fetchone()

            if row:
                return Document(
                    doc_id=row['doc_id'],
                    source_path=Path(row['source_path']) if row['source_path'] else None,
                    content_hash=row['content_hash'],
                    title=row['title'],
                    authors=row['authors'].split(',') if row['authors'] else [],
                    arxiv_id=row['arxiv_id'],
                    doi=row['doi'],
                    version=row['version'],
                    status=DocumentStatus(row['status']),
                    added_date=datetime.fromisoformat(row['added_date']),
                )
            return None

    def update_document_status(self, doc_id: str, status: DocumentStatus) -> bool:
        """Update document status.

        Args:
            doc_id: Document identifier
            status: New status

        Returns:
            True if updated successfully
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                UPDATE documents
                SET status = ?, updated_date = ?
                WHERE doc_id = ?
            """, (status.value, datetime.now().isoformat(), doc_id))
            return cursor.rowcount > 0

    def add_extraction(self, extraction: ExtractionResult) -> bool:
        """Add an extraction result to the registry.

        Args:
            extraction: Extraction result to add

        Returns:
            True if added successfully
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO extractions (
                        extraction_id, doc_id, extractor_name, extractor_version,
                        extraction_path, content, page_count, status, error_message, extraction_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    extraction.extraction_id,
                    extraction.doc_id,
                    extraction.extractor_name,
                    extraction.extractor_version,
                    str(extraction.extraction_path) if extraction.extraction_path else None,
                    extraction.content,
                    extraction.page_count,
                    extraction.status.value,
                    extraction.error_message,
                    extraction.extraction_date.isoformat(),
                ))
                return True
        except sqlite3.IntegrityError:
            return False

    def add_embedding(self, embedding: EmbeddingResult) -> bool:
        """Add an embedding result to the registry.

        Args:
            embedding: Embedding result to add

        Returns:
            True if added successfully
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO embeddings (
                        embedding_id, doc_id, extraction_id, embedder_name, embedder_version,
                        vector_db_path, chunk_count, embedding_date, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    embedding.embedding_id,
                    embedding.doc_id,
                    getattr(embedding, 'extraction_id', None),
                    embedding.embedder_name,
                    "1.0.0",  # Default version since EmbeddingResult doesn't have embedder_version
                    str(embedding.vector_db_path) if embedding.vector_db_path else None,
                    embedding.chunk_count,
                    embedding.indexed_date.isoformat() if embedding.indexed_date else datetime.now().isoformat(),
                    embedding.error_message,
                ))
                return True
        except sqlite3.IntegrityError:
            return False

    def get_documents_by_project(self, project_id: str) -> list[Document]:
        """Get all documents for a project.

        Args:
            project_id: Project identifier

        Returns:
            List of documents in the project
        """
        documents = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM documents WHERE project_id = ?
                ORDER BY added_date DESC
            """, (project_id,))

            for row in cursor.fetchall():
                documents.append(Document(
                    doc_id=row['doc_id'],
                    source_path=Path(row['source_path']) if row['source_path'] else None,
                    content_hash=row['content_hash'],
                    title=row['title'],
                    authors=row['authors'].split(',') if row['authors'] else [],
                    arxiv_id=row['arxiv_id'],
                    doi=row['doi'],
                    version=row['version'],
                    status=DocumentStatus(row['status']),
                    added_date=datetime.fromisoformat(row['added_date']),
                    project_id=row['project_id'],
                ))

        return documents

    def get_documents_by_status(self, status: DocumentStatus) -> list[Document]:
        """Get all documents with a specific status.

        Args:
            status: Document status to filter by

        Returns:
            List of documents with the specified status
        """
        documents = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM documents WHERE status = ?
                ORDER BY added_date DESC
            """, (status.value,))

            for row in cursor.fetchall():
                documents.append(Document(
                    doc_id=row['doc_id'],
                    source_path=Path(row['source_path']) if row['source_path'] else None,
                    content_hash=row['content_hash'],
                    title=row['title'],
                    authors=row['authors'].split(',') if row['authors'] else [],
                    arxiv_id=row['arxiv_id'],
                    doi=row['doi'],
                    version=row['version'],
                    status=DocumentStatus(row['status']),
                    added_date=datetime.fromisoformat(row['added_date']),
                    project_id=row['project_id'],
                ))

        return documents

    def document_exists(self, source_path: Path) -> bool:
        """Check if a document with the given source path exists.

        Args:
            source_path: Path to check

        Returns:
            True if document exists
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT 1 FROM documents WHERE source_path = ?
            """, (str(source_path),))
            return cursor.fetchone() is not None

    def get_document_by_path(self, source_path: Path) -> Document | None:
        """Get a document by source path.

        Args:
            source_path: Path to the source file

        Returns:
            Document if found, None otherwise
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM documents WHERE source_path = ?
            """, (str(source_path),))
            row = cursor.fetchone()

            if row:
                return Document(
                    doc_id=row['doc_id'],
                    source_path=Path(row['source_path']) if row['source_path'] else None,
                    content_hash=row['content_hash'],
                    title=row['title'],
                    authors=row['authors'].split(',') if row['authors'] else [],
                    arxiv_id=row['arxiv_id'],
                    doi=row['doi'],
                    version=row['version'],
                    status=DocumentStatus(row['status']),
                    added_date=datetime.fromisoformat(row['added_date']),
                )
            return None

    def get_processing_stats(self) -> dict[str, Any]:
        """Get processing statistics.

        Returns:
            Dictionary with processing statistics
        """
        with sqlite3.connect(self.db_path) as conn:
            # Document counts by status
            cursor = conn.execute("""
                SELECT status, COUNT(*) as count
                FROM documents
                GROUP BY status
            """)
            status_counts = dict(cursor.fetchall())

            # Total extractions
            cursor = conn.execute("SELECT COUNT(*) FROM extractions")
            total_extractions = cursor.fetchone()[0]

            # Total embeddings
            cursor = conn.execute("SELECT COUNT(*) FROM embeddings")
            total_embeddings = cursor.fetchone()[0]

            # Total chunks embedded
            cursor = conn.execute("SELECT SUM(chunk_count) FROM embeddings")
            total_chunks = cursor.fetchone()[0] or 0

            return {
                "total_documents": sum(status_counts.values()),
                "status_breakdown": status_counts,
                "total_extractions": total_extractions,
                "total_embeddings": total_embeddings,
                "total_chunks_embedded": total_chunks,
            }