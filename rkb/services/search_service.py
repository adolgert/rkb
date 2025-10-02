"""Search service for semantic search over document corpus."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import chromadb

from rkb.core.document_registry import DocumentRegistry
from rkb.core.models import ChunkResult, DocumentScore, SearchResult
from rkb.embedders.base import get_embedder

LOGGER = logging.getLogger("rkb.services.search_service")


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

    def close(self) -> None:
        """Close any open connections and clear cached objects."""
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

    def fetch_chunks_iteratively(  # noqa: PLR0912
        self,
        query: str,
        n_docs: int = 10,
        min_threshold: float = 0.1,
        filter_equations: bool | None = None,
        project_id: str | None = None,
    ) -> tuple[list[ChunkResult], dict[str, Any]]:
        """Fetch chunks iteratively until we have enough documents above threshold.

        This method implements the core iterative search loop for document-level search.
        It fetches chunks in batches until either:
        1. We have n_docs documents with chunks above min_threshold
        2. We reach the maximum chunk limit
        3. We exhaust all chunks in the database

        Args:
            query: Search query text
            n_docs: Number of documents to find
            min_threshold: Minimum similarity threshold for chunks
            filter_equations: Filter by presence of equations
            project_id: Filter by project ID

        Returns:
            Tuple of (all_chunks, stats_dict)
            - all_chunks: List of ChunkResult objects fetched
            - stats_dict: Statistics about the search (chunks_fetched, iterations, etc.)
        """
        # Configuration
        MAX_TOTAL_CHUNKS = 10000

        all_chunks: list[ChunkResult] = []
        iteration = 0
        chunks_per_iteration: list[int] = []

        try:
            collection = self._get_collection()

            # Prepare search filters
            where_filter = {}
            if filter_equations is not None:
                where_filter["has_equations"] = filter_equations
            if project_id is not None:
                where_filter["project_id"] = project_id

            while True:
                iteration += 1

                # Determine fetch size for this iteration
                if iteration == 1:
                    # Initial fetch: get n_docs * 5 chunks
                    # We need to fetch all at once since ChromaDB doesn't support offset
                    fetch_size = MAX_TOTAL_CHUNKS  # Fetch all up to limit
                else:
                    # No more iterations needed - we fetch everything in first iteration
                    break

                # Perform search
                search_kwargs = {
                    "query_texts": [query],
                    "n_results": min(fetch_size, MAX_TOTAL_CHUNKS),
                }

                if where_filter:
                    search_kwargs["where"] = where_filter

                results = collection.query(**search_kwargs)

                # Convert to ChunkResult format
                if results and results["documents"] and results["documents"][0]:
                    documents = results["documents"][0]
                    metadatas = results["metadatas"][0]
                    distances = results["distances"][0]
                    ids = results["ids"][0] if results["ids"] else [None] * len(documents)

                    batch_chunks = []
                    for doc, metadata, distance, chunk_id in zip(
                        documents, metadatas, distances, ids, strict=True
                    ):
                        # Convert distance to similarity score
                        similarity = 1 / (1 + distance) if distance is not None else 0.0

                        chunk_result = ChunkResult(
                            chunk_id=chunk_id or f"chunk_{len(all_chunks)}",
                            content=doc,
                            similarity=similarity,
                            distance=distance,
                            metadata=metadata or {},
                        )
                        batch_chunks.append(chunk_result)

                    all_chunks.extend(batch_chunks)
                    chunks_per_iteration.append(len(batch_chunks))

                    LOGGER.info(
                        f"Iteration {iteration}: fetched {len(batch_chunks)} chunks, "
                        f"total: {len(all_chunks)}"
                    )

                    # Check if we got fewer chunks than requested (database exhausted)
                    if len(batch_chunks) < fetch_size:
                        LOGGER.info("Database exhausted - got fewer chunks than requested")
                        break
                else:
                    # No results in this batch
                    chunks_per_iteration.append(0)
                    break

                # Check termination: do we have enough documents above threshold?
                chunks_above_threshold = [
                    chunk for chunk in all_chunks if chunk.similarity >= min_threshold
                ]

                # Group by document to count documents
                docs_found = set()
                for chunk in chunks_above_threshold:
                    if "doc_id" in chunk.metadata:
                        docs_found.add(chunk.metadata["doc_id"])

                LOGGER.info(
                    f"After iteration {iteration}: {len(docs_found)} documents "
                    f"with chunks above threshold {min_threshold}"
                )

                if len(docs_found) >= n_docs:
                    LOGGER.info(f"Found enough documents ({len(docs_found)} >= {n_docs})")
                    break

                # Safety limit check
                if len(all_chunks) >= MAX_TOTAL_CHUNKS:
                    LOGGER.warning(
                        f"Reached maximum chunk limit ({MAX_TOTAL_CHUNKS}), "
                        "terminating search"
                    )
                    break

            # Prepare statistics
            chunks_above_threshold = [
                chunk for chunk in all_chunks if chunk.similarity >= min_threshold
            ]
            docs_found = set()
            for chunk in chunks_above_threshold:
                if "doc_id" in chunk.metadata:
                    docs_found.add(chunk.metadata["doc_id"])

            stats = {
                "chunks_fetched": len(all_chunks),
                "chunks_above_threshold": len(chunks_above_threshold),
                "iterations": iteration,
                "documents_found": len(docs_found),
                "chunks_per_iteration": chunks_per_iteration,
            }

            return all_chunks, stats

        except Exception as e:
            LOGGER.exception("Error in fetch_chunks_iteratively")
            return [], {
                "chunks_fetched": 0,
                "chunks_above_threshold": 0,
                "iterations": iteration,
                "documents_found": 0,
                "error": str(e),
            }

    def rank_by_similarity(
        self,
        chunks: list[ChunkResult],
    ) -> list[DocumentScore]:
        """Rank documents by similarity using max pooling.

        For each document, takes the maximum chunk score as the document score.

        Args:
            chunks: List of chunk results to rank

        Returns:
            List of DocumentScore objects sorted by score descending
        """
        # Group chunks by document
        doc_chunks: dict[str, list[ChunkResult]] = {}
        for chunk in chunks:
            doc_id = chunk.metadata.get("doc_id")
            if doc_id:
                if doc_id not in doc_chunks:
                    doc_chunks[doc_id] = []
                doc_chunks[doc_id].append(chunk)

        # Compute max score for each document
        doc_scores = []
        for doc_id, doc_chunk_list in doc_chunks.items():
            max_score = max(chunk.similarity for chunk in doc_chunk_list)
            doc_score = DocumentScore(
                doc_id=doc_id,
                score=max_score,
                metric_name="similarity",
                best_chunk_score=max_score,
                matching_chunk_count=len(doc_chunk_list),
            )
            doc_scores.append(doc_score)

        # Sort by score descending
        doc_scores.sort(key=lambda x: x.score, reverse=True)
        return doc_scores

    def rank_by_relevance(
        self,
        chunks: list[ChunkResult],
        min_threshold: float,
    ) -> list[DocumentScore]:
        """Rank documents by relevance using hit counting.

        For each document, counts how many chunks have score > threshold.

        Args:
            chunks: List of chunk results to rank
            min_threshold: Minimum similarity threshold for counting hits

        Returns:
            List of DocumentScore objects sorted by hit count descending
        """
        # Group chunks by document
        doc_chunks: dict[str, list[ChunkResult]] = {}
        for chunk in chunks:
            doc_id = chunk.metadata.get("doc_id")
            if doc_id:
                if doc_id not in doc_chunks:
                    doc_chunks[doc_id] = []
                doc_chunks[doc_id].append(chunk)

        # Count hits for each document
        doc_scores = []
        for doc_id, doc_chunk_list in doc_chunks.items():
            # Count chunks above threshold
            hit_count = sum(1 for chunk in doc_chunk_list if chunk.similarity >= min_threshold)

            # Also track best chunk score for this document
            max_score = max(chunk.similarity for chunk in doc_chunk_list)

            doc_score = DocumentScore(
                doc_id=doc_id,
                score=float(hit_count),  # Use hit count as score
                metric_name="relevance",
                matching_chunk_count=hit_count,
                best_chunk_score=max_score,
            )
            doc_scores.append(doc_score)

        # Sort by hit count descending, then by best chunk score
        doc_scores.sort(key=lambda x: (x.score, x.best_chunk_score or 0), reverse=True)
        return doc_scores

    def get_display_data(
        self,
        doc_score: DocumentScore,
        chunks: list[ChunkResult],
        strategy: str = "top_chunk",
    ) -> dict[str, Any]:
        """Get display data for a document score.

        Args:
            doc_score: DocumentScore to get display data for
            chunks: All chunks (needed to find chunks for this document)
            strategy: Display strategy ("top_chunk", "top_n", "all_matching", "summary")

        Returns:
            Dictionary with display information:
            - chunk_text: Text of the best matching chunk
            - chunk_score: Score of the best matching chunk
            - page_numbers: List of page numbers for the chunk
            - chunk_id: ID of the best matching chunk
        """
        # Find chunks for this document
        doc_chunks = [
            chunk for chunk in chunks
            if chunk.metadata.get("doc_id") == doc_score.doc_id
        ]

        if not doc_chunks:
            return {
                "chunk_text": None,
                "chunk_score": None,
                "page_numbers": [],
                "chunk_id": None,
                "error": "No chunks found for document",
            }

        if strategy == "top_chunk":
            # Return best matching chunk
            best_chunk = max(doc_chunks, key=lambda x: x.similarity)
            return {
                "chunk_text": best_chunk.content,
                "chunk_score": best_chunk.similarity,
                "page_numbers": best_chunk.metadata.get("page_numbers", []),
                "chunk_id": best_chunk.chunk_id,
            }

        # Future strategies can be implemented here
        # For now, default to top_chunk
        best_chunk = max(doc_chunks, key=lambda x: x.similarity)
        return {
            "chunk_text": best_chunk.content,
            "chunk_score": best_chunk.similarity,
            "page_numbers": best_chunk.metadata.get("page_numbers", []),
            "chunk_id": best_chunk.chunk_id,
        }

    def search_documents_ranked(
        self,
        query: str,
        n_docs: int = 10,
        metric: str = "similarity",
        min_threshold: float | None = None,
        filter_equations: bool | None = None,
        project_id: str | None = None,
    ) -> tuple[list[DocumentScore], list[ChunkResult], dict[str, Any]]:
        """Search and rank documents using document-level metrics.

        This is the main entry point for document-level search. It:
        1. Fetches chunks iteratively until N documents found
        2. Ranks documents using the specified metric
        3. Returns top N documents with all chunks for display data

        Args:
            query: Search query text
            n_docs: Number of documents to return (default: 10)
            metric: Ranking metric - "similarity" (max pooling) or "relevance" (hit counting)
            min_threshold: Minimum similarity threshold (if None, uses embedder default)
            filter_equations: Filter by presence of equations
            project_id: Filter by project ID

        Returns:
            Tuple of (ranked_docs, all_chunks, stats):
            - ranked_docs: List of DocumentScore objects (top N, sorted by score)
            - all_chunks: All chunks fetched (needed for display data)
            - stats: Search statistics (chunks_fetched, iterations, etc.)
        """
        # Get threshold from embedder if not provided
        if min_threshold is None:
            min_threshold = self.embedder.minimum_threshold

        # Step 1: Fetch chunks iteratively
        all_chunks, stats = self.fetch_chunks_iteratively(
            query=query,
            n_docs=n_docs,
            min_threshold=min_threshold,
            filter_equations=filter_equations,
            project_id=project_id,
        )

        # Step 2: Rank documents by chosen metric
        if metric == "similarity":
            ranked_docs = self.rank_by_similarity(all_chunks)
        elif metric == "relevance":
            ranked_docs = self.rank_by_relevance(all_chunks, min_threshold)
        else:
            raise ValueError(
                f"Unknown metric '{metric}'. Expected 'similarity' or 'relevance'"
            )

        # Step 3: Return top N documents
        top_n_docs = ranked_docs[:n_docs]

        # Log search completion
        LOGGER.info(
            f"Document search complete: query='{query}', metric={metric}, "
            f"found {len(top_n_docs)} documents (fetched {stats['chunks_fetched']} "
            f"chunks in {stats['iterations']} iterations)"
        )

        return top_n_docs, all_chunks, stats

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

                for doc, metadata, distance, chunk_id in zip(
                    documents, metadatas, distances, ids, strict=True
                ):
                    # Convert distance to similarity score using inverse distance formula
                    similarity = 1 / (1 + distance) if distance is not None else 0.0

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

                for doc, metadata, distance, found_chunk_id in zip(
                    documents, metadatas, distances, ids, strict=True
                ):
                    # Skip the reference chunk itself
                    if found_chunk_id == chunk_id:
                        continue

                    # Convert distance to similarity score using inverse distance formula
                    similarity = 1 / (1 + distance) if distance is not None else 0.0
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

    def test_search(self, test_query: str = "machine learning") -> SearchResult:  # noqa: T201
        """Test search functionality with a sample query.

        Args:
            test_query: Query to test with

        Returns:
            SearchResult from test query
        """
        msg = f"🧪 Testing search with query: '{test_query}'"
        LOGGER.info(msg)
        result = self.search_documents(test_query, n_results=3)

        if result.error_message:
            msg = f"✗ Search test failed: {result.error_message}"
            LOGGER.error(msg)
        elif result.total_results > 0:
            msg = f"✓ Search test successful - found {result.total_results} results"
            LOGGER.info(msg)
        else:
            msg = "⚠ Search test returned no results (may be normal)"
            LOGGER.warning(msg)

        return result

    def display_results(  # noqa: T201
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
            msg = f"✗ Search error: {search_result.error_message}"
            print(msg)  # noqa: T201
            return

        if search_result.total_results == 0:
            print("No results found.")  # noqa: T201
            return

        msg = f"\n📊 Found {search_result.total_results} results for: '{search_result.query}'"
        print(msg)  # noqa: T201
        if search_result.filters_applied:
            msg = f"🔧 Filters: {search_result.filters_applied}"
            print(msg)  # noqa: T201
        print("=" * 80)  # noqa: T201

        for i, chunk in enumerate(search_result.chunk_results):
            msg = f"\n🔖 Result {i+1} (similarity: {chunk.similarity:.3f})"
            print(msg)  # noqa: T201

            # Extract common metadata fields
            metadata = chunk.metadata
            if "pdf_name" in metadata:
                chunk_idx = metadata.get("chunk_index", "?")
                msg = f"📄 Source: {metadata['pdf_name']} (chunk {chunk_idx})"
                print(msg)  # noqa: T201
            elif "doc_id" in metadata:
                msg = f"📄 Document: {metadata['doc_id']}"
                print(msg)  # noqa: T201

            if "has_equations" in metadata:
                eq_display = metadata.get("display_eq_count", 0)
                eq_inline = metadata.get("inline_eq_count", 0)
                has_eq = "✓" if metadata["has_equations"] else "✗"
                msg = f"🧮 Equations: {has_eq} (Display: {eq_display}, Inline: {eq_inline})"
                print(msg)  # noqa: T201

            if show_content:
                content = chunk.content[:max_content_length]
                if len(chunk.content) > max_content_length:
                    content += "..."
                msg = f"📝 Content:\n{content}"
                print(msg)  # noqa: T201

            print("-" * 80)  # noqa: T201

        # Show average similarity
        if search_result.chunk_results:
            avg_similarity = search_result.avg_score
            msg = f"\n📈 Average similarity: {avg_similarity:.3f}"
            print(msg)  # noqa: T201
