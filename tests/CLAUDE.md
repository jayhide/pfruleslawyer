# Tests Directory

Pytest test suite for the pfruleslawyer package.

## Structure

### unit/
Fast unit tests that don't require external resources:
- `test_preprocess_sections.py` - Tests for source name generation and suffix stripping

### integration/
Tests that require the full index/database:
- `test_vector_store.py` - Search retrieval accuracy tests

## Running Tests

```bash
# All tests
poetry run pytest

# Verbose output
poetry run pytest -v

# Unit tests only (fast)
poetry run pytest tests/unit/

# Integration tests only (requires index)
poetry run pytest tests/integration/

# Specific file
poetry run pytest tests/unit/test_preprocess_sections.py
```

## Adding Tests

- Add regression tests to `integration/test_vector_store.py` when search fails
- Use `assert_retrieved()` helper to check if expected sections appear in results
