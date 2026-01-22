# Config Directory

Configuration files for preprocessing and indexing.

## Files

### preprocess_config.json
Main configuration for URL processing:
- `entries` - List of URL patterns with processing modes and categories
- `category_weights` - Search weight customization per category

Example entry:
```json
{
  "pattern": "https://www.d20pfsrd.com/magic/all-spells/*",
  "mode": "template",
  "category": "Spells",
  "name_prefix": "Spell"
}
```

### class_secondary_urls.json
URLs for secondary class features (archetypes, bloodlines, etc.) that need special handling during class document processing.

## Category Weights

Categories can customize search behavior:
```json
{
  "Spells": {
    "semantic_weight": 0.0,  // No embedding, title-only matching
    "title_boost": 1.0,
    "rerank_weight": 0.2
  }
}
```

Setting `semantic_weight: 0` makes sections metadata-only (faster indexing, title-based retrieval).

## Disambiguation Rules

Prevents title matches when ambiguous terms appear in specific contexts:
```json
{
  "disambiguation_rules": {
    "medium": {
      "negative_contexts": [
        "medium armor",
        "medium size",
        "size medium"
      ]
    }
  }
}
```

- Keys are **lemmatized** (lowercase) to match the title index format
- When a query contains any `negative_contexts` phrase, the title match is suppressed
- Matching is case-insensitive against the original query text
- Use this to prevent false positives like "Medium" archetype matching "medium armor" queries
