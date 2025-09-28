"""Search service for semantic search over document corpus."""

from datetime import datetime
from pathlib import Path
from typing import Any

import chromadb

from rkb.core.document_registry import DocumentRegistry
from rkb.core.models import SearchResult, ChunkResult
from rkb.embedders.base import get_embedder


class SearchService:
    """Service for semantic search operations over document corpus."""

    def __init__(
        self,
        db_path: str | Path = "rkb_chroma_db",
        collection_name: str = "documents",
        embedder_name: str = "chroma",
        registry: DocumentRegistry | None = None,
    ):
        """Initialize search service.

        Args:
            db_path: Path to Chroma database
            collection_name: Name of Chroma collection
            embedder_name: Name of embedder to use for query embedding
            registry: Document registry for metadata lookup
        """
        self.db_path = Path(db_path)
        self.collection_name = collection_name
        self.embedder_name = embedder_name
        self.registry = registry or DocumentRegistry()

        # Initialize embedder for query processing
        self.embedder = get_embedder(embedder_name)

        # Initialize Chroma client
        self._chroma_client = None
        self._collection = None

    def _get_collection(self):
        """Get or create Chroma collection."""
        if self._chroma_client is None:
            self._chroma_client = chromadb.PersistentClient(path=str(self.db_path))

        if self._collection is None:
            try:
                self._collection = self._chroma_client.get_collection(self.collection_name)
            except Exception:
                # Collection doesn't exist, create it
                self._collection = self._chroma_client.create_collection(
                    name=self.collection_name,
                    metadata={
                        "description": "RKB document search collection",
                        "created": datetime.now().isoformat(),
                    },
                )

        return self._collection

    def search_documents(
        self,
        query: str,
        n_results: int = 5,
        filter_equations: bool | None = None,
        project_id: str | None = None,
        document_ids: list[str] | None = None,
    ) -> SearchResult:
        """Search documents using semantic similarity.

        Args:
            query: Search query text
            n_results: Maximum number of results to return
            filter_equations: Filter by presence of equations (True/False/None)
            project_id: Filter by project ID
            document_ids: Filter by specific document IDs

        Returns:
            SearchResult with matched chunks and metadata
        """
        try:
            collection = self._get_collection()

            # Prepare search filters
            where_filter = {}
            if filter_equations is not None:
                where_filter["has_equations"] = filter_equations
            if project_id is not None:
                where_filter["project_id"] = project_id
            if document_ids is not None:
                where_filter["doc_id"] = {"$in": document_ids}

            # Perform search using query text (let Chroma handle embedding)
            search_kwargs = {
                "query_texts": [query],
                "n_results": min(n_results, 100),  # Reasonable limit
            }

            if where_filter:
                search_kwargs["where"] = where_filter

            results = collection.query(**search_kwargs)

            # Convert to SearchResult format
            chunk_results = []
            if results and results["documents"] and results["documents"][0]:
                documents = results["documents"][0]
                metadatas = results["metadatas"][0]
                distances = results["distances"][0]
                ids = results["ids"][0] if results["ids"] else [None] * len(documents)

                for doc, metadata, distance, chunk_id in zip(documents, metadatas, distances, ids):
                    # Convert distance to similarity score
                    similarity = 1 - distance if distance is not None else 0.0

                    chunk_result = ChunkResult(
                        chunk_id=chunk_id or f"chunk_{len(chunk_results)}",
                        content=doc,
                        similarity=similarity,
                        distance=distance,
                        metadata=metadata or {},
                    )
                    chunk_results.append(chunk_result)

            return SearchResult(
                query=query,
                chunk_results=chunk_results,
                total_results=len(chunk_results),
                search_time=0.0,  # Could add timing if needed
                filters_applied={
                    "equations": filter_equations,
                    "project_id": project_id,
                    "document_ids": document_ids,
                },
            )

        except Exception as e:
            # Return empty result with error info
            return SearchResult(
                query=query,
                chunk_results=[],
                total_results=0,
                search_time=0.0,
                error_message=str(e),
            )

    def search_by_document(
        self,
        query: str,
        doc_id: str,
        n_results: int = 5,
    ) -> SearchResult:
        """Search within a specific document.

        Args:
            query: Search query text
            doc_id: Document ID to search within
            n_results: Maximum number of results to return

        Returns:
            SearchResult with matched chunks from the document
        """
        return self.search_documents(
            query=query,
            n_results=n_results,
            document_ids=[doc_id],
        )

    def get_similar_chunks(
        self,
        chunk_id: str,
        n_results: int = 5,
        exclude_same_document: bool = True,
    ) -> SearchResult:
        """Find chunks similar to a given chunk.

        Args:
            chunk_id: ID of the reference chunk
            n_results: Maximum number of results to return
            exclude_same_document: Whether to exclude chunks from same document

        Returns:
            SearchResult with similar chunks
        """
        try:
            collection = self._get_collection()

            # Get the reference chunk
            ref_chunks = collection.get(ids=[chunk_id])
            if not ref_chunks or not ref_chunks["documents"]:
                return SearchResult(
                    query=f"similar_to:{chunk_id}",
                    chunk_results=[],
                    total_results=0,
                    error_message=f"Reference chunk {chunk_id} not found",
                )

            ref_text = ref_chunks["documents"][0]
            ref_metadata = ref_chunks["metadatas"][0] if ref_chunks["metadatas"] else {}

            # Build filters
            where_filter = {}
            if exclude_same_document and "doc_id" in ref_metadata:
                where_filter["doc_id"] = {"$ne": ref_metadata["doc_id"]}

            # Search for similar chunks using reference text
            search_kwargs = {
                "query_texts": [ref_text],
                "n_results": n_results + 1,  # +1 to account for excluding self
            }

            if where_filter:
                search_kwargs["where"] = where_filter

            results = collection.query(**search_kwargs)

            # Process results and exclude the reference chunk itself
            chunk_results = []
            if results and results["documents"] and results["documents"][0]:
                documents = results["documents"][0]
                metadatas = results["metadatas"][0]
                distances = results["distances"][0]
                ids = results["ids"][0] if results["ids"] else [None] * len(documents)

                for doc, metadata, distance, found_chunk_id in zip(documents, metadatas, distances, ids):
                    # Skip the reference chunk itself
                    if found_chunk_id == chunk_id:
                        continue

                    similarity = 1 - distance if distance is not None else 0.0
                    chunk_result = ChunkResult(
                        chunk_id=found_chunk_id or f"chunk_{len(chunk_results)}",
                        content=doc,
                        similarity=similarity,
                        distance=distance,
                        metadata=metadata or {},
                    )
                    chunk_results.append(chunk_result)

                    # Stop if we have enough results
                    if len(chunk_results) >= n_results:
                        break

            return SearchResult(
                query=f"similar_to:{chunk_id}",
                chunk_results=chunk_results,
                total_results=len(chunk_results),
                filters_applied={
                    "exclude_same_document": exclude_same_document,
                    "reference_chunk": chunk_id,
                },
            )

        except Exception as e:
            return SearchResult(
                query=f"similar_to:{chunk_id}",
                chunk_results=[],
                total_results=0,
                error_message=str(e),
            )

    def get_database_stats(self) -> dict[str, Any]:
        """Get statistics about the search database.

        Returns:
            Dictionary with database statistics
        """
        try:
            collection = self._get_collection()
            total_chunks = collection.count()

            # Sample some documents to get equation statistics
            sample_size = min(1000, total_chunks)
            if sample_size > 0:
                sample = collection.get(limit=sample_size)
                if sample and sample["metadatas"]:
                    eq_chunks = sum(1 for m in sample["metadatas"] if m.get("has_equations", False))
                    eq_percentage = (eq_chunks / len(sample["metadatas"])) * 100
                else:
                    eq_percentage = 0.0
            else:
                eq_percentage = 0.0

            # Get processing stats from registry
            registry_stats = self.registry.get_processing_stats()

            return {
                "total_chunks": total_chunks,
                "equation_percentage": round(eq_percentage, 1),
                "collection_name": self.collection_name,
                "db_path": str(self.db_path),
                "embedder": self.embedder_name,
                "registry_stats": registry_stats,
                "sample_size": sample_size,
            }

        except Exception as e:
            return {
                "total_chunks": 0,
                "equation_percentage": 0.0,
                "error": str(e),
            }

    def test_search(self, test_query: str = "machine learning") -> SearchResult:
        """Test search functionality with a sample query.

        Args:
            test_query: Query to test with

        Returns:
            SearchResult from test query
        """
        print(f"🧪 Testing search with query: '{test_query}'")
        result = self.search_documents(test_query, n_results=3)

        if result.error_message:
            print(f"✗ Search test failed: {result.error_message}")
        elif result.total_results > 0:
            print(f"✓ Search test successful - found {result.total_results} results")
        else:
            print("⚠ Search test returned no results (may be normal)")

        return result

    def display_results(
        self,
        search_result: SearchResult,
        show_content: bool = True,
        max_content_length: int = 300,
    ) -> None:
        """Display search results in a readable format.

        Args:
            search_result: SearchResult to display
            show_content: Whether to show chunk content
            max_content_length: Maximum length of content to display
        """
        if search_result.error_message:
            print(f"✗ Search error: {search_result.error_message}")
            return

        if search_result.total_results == 0:
            print("No results found.")
            return

        print(f"\n📊 Found {search_result.total_results} results for: '{search_result.query}'")
        if search_result.filters_applied:
            print(f"🔧 Filters: {search_result.filters_applied}")
        print("=" * 80)

        for i, chunk in enumerate(search_result.chunk_results):
            print(f"\n🔖 Result {i+1} (similarity: {chunk.similarity:.3f})")

            # Extract common metadata fields
            metadata = chunk.metadata
            if "pdf_name" in metadata:
                chunk_idx = metadata.get("chunk_index", "?")
                print(f"📄 Source: {metadata['pdf_name']} (chunk {chunk_idx})")
            elif "doc_id" in metadata:
                print(f"📄 Document: {metadata['doc_id']}")

            if "has_equations" in metadata:
                eq_display = metadata.get("display_eq_count", 0)
                eq_inline = metadata.get("inline_eq_count", 0)
                has_eq = "✓" if metadata["has_equations"] else "✗"
                print(f"🧮 Equations: {has_eq} (Display: {eq_display}, Inline: {eq_inline})")

            if show_content:
                content = chunk.content[:max_content_length]
                if len(chunk.content) > max_content_length:
                    content += "..."
                print(f"📝 Content:\n{content}")

            print("-" * 80)

        # Show average similarity
        if search_result.chunk_results:
            avg_similarity = search_result.avg_score
            print(f"\n📈 Average similarity: {avg_similarity:.3f}")