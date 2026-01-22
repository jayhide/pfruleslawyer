# Unit Tests

Fast unit tests that don't require external resources (database, vector store, API calls).

## Files

- `test_disambiguation.py` - Tests for title disambiguation in vector store
- `test_preprocess_sections.py` - Tests for source name generation and suffix stripping
- `test_reranker.py` - Tests for reranker module (LLM and cross-encoder)
- `test_rules_lawyer_dedup.py` - Tests for search result deduplication

## Test Coverage

### test_disambiguation.py

Tests for `pfruleslawyer.search.vector_store` disambiguation:

- `TestDisambiguationRules` - Negative context detection suppressing title matches (e.g., "medium armor" query should not match "Medium" archetype)
- `TestDisambiguationConfigLoading` - Loading disambiguation_rules from config file

### test_preprocess_sections.py

Tests for `pfruleslawyer.preprocessing.processor`:

- `TestGetSourceName` - Source name generation from file paths (mapped names, category templates, fallbacks)
- `TestStripFeatSuffix` - Feat type suffix removal: (Combat), (Combat, Style), (Achievement), etc.
- `TestStripAbilityTypeSuffix` - Ability type suffix removal: (Ex), (Su), (Sp)

### test_reranker.py

Tests for `pfruleslawyer.search.reranker`:

- `TestExtractScoresFromResponse` - LLM response parsing (JSON, regex fallback, clamping)
- `TestFormatDocForLlm` - Document formatting for LLM prompt
- `TestRerankWithLlm` - LLM reranking with mocked Anthropic client
- `TestComputeCombinedScores` - Score normalization and weighted combination
- `TestRerankDispatch` - Dispatch logic between LLM and cross-encoder
- `TestRerankerModelRegistry` - Model registry validation

## Running

```bash
poetry run pytest tests/unit/ -v
```

## Adding Unit Tests

Place tests here when:
- Testing pure functions with no external dependencies
- Testing data transformations or parsing logic
- Tests can run without database or vector index
