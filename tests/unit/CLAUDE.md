# Unit Tests

Fast unit tests that don't require external resources (database, vector store, API calls).

## Files

- `test_preprocess_sections.py` - Tests for source name generation and suffix stripping

## Test Coverage

### test_preprocess_sections.py

Tests for `pfruleslawyer.preprocessing.processor`:

- `TestGetSourceName` - Source name generation from file paths (mapped names, category templates, fallbacks)
- `TestStripFeatSuffix` - Feat type suffix removal: (Combat), (Combat, Style), (Achievement), etc.
- `TestStripAbilityTypeSuffix` - Ability type suffix removal: (Ex), (Su), (Sp)

## Running

```bash
poetry run pytest tests/unit/ -v
```

## Adding Unit Tests

Place tests here when:
- Testing pure functions with no external dependencies
- Testing data transformations or parsing logic
- Tests can run without database or vector index
