# Search Module

Vector-based semantic search over rules sections.

## Files

- `vector_store.py` - `RulesVectorStore` class using ChromaDB
- `lemmatizer.py` - `Lemmatizer` singleton for word normalization
- `reranker.py` - `Reranker` singleton for cross-encoder reranking

## Key Classes

### RulesVectorStore
Main search interface using ChromaDB for embeddings.

```python
store = RulesVectorStore()
results = store.query("how does grappling work", n_results=5)
```

Features:
- Semantic similarity search via sentence-transformers
- Exact keyword/title matching with configurable boosts
- Cross-encoder reranking for improved relevance
- Category-specific weights (e.g., spells use title-only matching)
- Link resolution with URL fragment support

### Lemmatizer
Hybrid spaCy + Porter stemmer for word normalization.
- Handles both common English and domain-specific terms (e.g., "polymorph")

### Reranker
Reranking models for improving search result relevance.

Available models:
- `ms-marco` (default): Fast cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`), ~50-200ms
- `bge-large`: Higher quality cross-encoder (`BAAI/bge-reranker-large`), ~100-400ms
- `llm-haiku`: LLM-based reranker using Claude 3.5 Haiku, ~200-500ms

The LLM reranker evaluates passage relevance on a 1-5 scale, which is normalized to 0-1 for compatibility with the weighted scoring system. On API errors or parse failures, it falls back to neutral scores (3).

All rerankers combine their relevance score with the retrieval score using configurable weights (default: 40% rerank, 60% retrieval).

## Index Types

Sections are split into two storage types based on category weights:
- **Semantic sections**: Embedded in ChromaDB (categories with `semantic_weight > 0`)
- **Metadata-only sections**: Stored in JSON for title matching only (spells, archetypes)
