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
Cross-encoder model (`ms-marco-MiniLM-L-6-v2`) for reranking search results.
- Combines retrieval score with cross-encoder relevance

## Index Types

Sections are split into two storage types based on category weights:
- **Semantic sections**: Embedded in ChromaDB (categories with `semantic_weight > 0`)
- **Metadata-only sections**: Stored in JSON for title matching only (spells, archetypes)
