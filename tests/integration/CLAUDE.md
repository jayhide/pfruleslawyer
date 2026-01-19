# Integration Tests

Tests that require the full vector index and/or database.

## Files

- `test_vector_store.py` - Search retrieval accuracy tests

## Test Coverage

### test_vector_store.py

Search quality regression tests using `RulesVectorStore`:

- `TestTitleMatching` - Exact title/keyword matching (fireball, grapple)
- `TestSemanticSearch` - Conceptual query matching (how does grappling work)
- `TestRegressionCases` - Previously failing search cases

## Running

```bash
# Requires built vector index
poetry run pfrules-vectordb --build  # if not already built
poetry run pytest tests/integration/ -v
```

## Adding Regression Tests

When a search fails to return expected results:

1. Add a test case to `TestRegressionCases`
2. Use the `assert_retrieved()` helper:
   ```python
   def test_my_failing_case(self, store):
       results = store.query("my query", n_results=10)
       assert_retrieved(results, title_contains="Expected Title", top_n=5)
   ```
3. Fix the underlying issue and verify the test passes

## assert_retrieved() Options

- `section_id` - Exact section ID to find
- `title_contains` - Substring in title (case-insensitive)
- `source_contains` - Substring in source_name (case-insensitive)
- `top_n` - Section must appear in top N results (default: anywhere)
