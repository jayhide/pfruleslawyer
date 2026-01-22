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
- `warmup()` method eagerly loads spaCy model to avoid first-query latency

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

## Precomputed Lemmatized Indices

During `--build`, lemmatized indices are precomputed and saved to `data/vectordb/lemmatized_indices.json`. This eliminates the 600-1400ms latency that would otherwise occur on first query when indices are built dynamically.

**File format** (`lemmatized_indices.json`):
```json
{
  "version": 1,
  "keyword_index": {"<lemmatized_keyword>": ["<unique_id>", ...]},
  "title_index": {"<lemmatized_title>": ["<unique_id>", ...]},
  "subheading_index": {"<lemmatized_subheading>": ["<unique_id>", ...]},
  "section_metadata": {"<unique_id>": {...}},
  "url_index": {"<normalized_url>": ["<unique_id>", ...]},
  "heading_to_section": {"<url>": {"<heading>": "<unique_id>"}},
  "anchor_id_index": {"<url>": {"<anchor_id>": "<unique_id>"}}
}
```

**Server warmup**: The web server (`app.py`) eagerly loads the lemmatizer and keyword indices at startup, so even the first request has minimal latency.

**Backward compatibility**: If `lemmatized_indices.json` is missing (e.g., old builds), indices are built dynamically on first query. A version mismatch prints a warning and also triggers dynamic rebuild.

## Title Disambiguation

Titles that match common words can cause false positives (e.g., "Medium" archetype matching "medium armor" queries). The `disambiguation_rules` config section defines negative contexts that suppress title matches:

```python
# In _find_exact_matches(), before title matching:
if title in self._disambiguation_rules:
    negative_contexts = self._disambiguation_rules[title].get("negative_contexts", [])
    if any(ctx.lower() in query_lower for ctx in negative_contexts):
        continue  # Skip this title
```

Rules are defined in `config/preprocess_config.json` with lemmatized keys.
