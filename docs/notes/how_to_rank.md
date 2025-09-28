  Your system currently returns individual chunks with similarity scores (cosine distance). To turn this into true semantic search that can identify articles, chapters, or entire documents, we need several strategies:

  Key Strategies for Document-Level Semantic Search

  1. Similarity Score Cutoffs

  - Dynamic thresholding: Use distance statistics to set adaptive cutoffs (e.g., mean + 2*std)
  - Fixed thresholds: Common ranges for cosine distance:
    - < 0.3: Very relevant
    - 0.3-0.5: Relevant
    - 0.5-0.7: Somewhat relevant
    0.7: Low relevance
  - Top-K with minimum threshold: Return top 10 results but only if distance < 0.6

  2. Document-Level Aggregation

  Methods to combine chunk scores into document scores:
  - Max pooling: Document score = best chunk score
  - Average pooling: Document score = mean of top-3 chunks per document
  - Weighted aggregation: Weight by chunk position, equation density, or length
  - Hit counting: Number of chunks from document in top-20 results

  3. Chapter/Section Detection

  - Add hierarchical metadata during indexing (chapter_id, section_name)
  - Use markdown headers to identify logical boundaries
  - Group consecutive chunks that score well together

  4. Ranking Strategies

  - BM25 + Vector hybrid: Combine keyword and semantic scores
  - Re-ranking with cross-encoders: Use a second model to re-score top results
  - Diversity optimization: Ensure results come from different documents/sections
  - Recency bias: Weight by document date for time-sensitive queries

  5. Query Expansion

  - Generate multiple embeddings from paraphrased queries
  - Use LLM to extract key concepts and search for each
  - Implement pseudo-relevance feedback
