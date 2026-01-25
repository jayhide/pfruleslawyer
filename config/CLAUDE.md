# Config Directory

Configuration files for preprocessing and indexing.

## Files

### preprocess_config.yaml

Main configuration for URL processing in YAML format. YAML supports:
- Comments for documentation
- YAML anchors for reducing repetition
- More readable multi-line strings

### class_secondary_urls.json

URLs for secondary class features (archetypes, bloodlines, etc.) that need special handling during class document processing.

## Configuration Structure

### Disambiguation Rules

Prevents title matches when ambiguous terms appear in specific contexts:
```yaml
disambiguation_rules:
  medium:  # lemmatized key
    negative_contexts:
      - medium armor
      - medium size
```

- Keys are **lemmatized** (lowercase) to match the title index format
- When a query contains any `negative_contexts` phrase, the title match is suppressed
- Use this to prevent false positives like "Medium" archetype matching "medium armor" queries

### Category Weights

Configure search behavior per category. YAML anchors reduce repetition:
```yaml
category_weights:
  _default:
    semantic_weight: 1.0
    keyword_boost: 0.2
    subheading_boost: 0.2
    title_boost: 0.3
    rerank_weight: 0.1

  # Define reusable anchor
  _title_only: &title_only
    semantic_weight: 0.0
    keyword_boost: 0.0
    subheading_boost: 0.0
    title_boost: 1.0
    rerank_weight: 0.1

  # Reference the anchor
  Spells: *title_only
  Feats: *title_only
  Archetypes: *title_only
```

Setting `semantic_weight: 0` makes sections metadata-only (faster indexing, title-based retrieval).

### Entries

URL patterns and their processing configuration:

```yaml
entries:
  # Single URL
  - url: https://www.d20pfsrd.com/gamemastering/combat/
    mode: full
    category: Core Rules
    name: Combat Rules

  # Multiple URLs
  - urls:
      - https://www.d20pfsrd.com/equipment/weapons/
      - https://www.d20pfsrd.com/equipment/armor/
    mode: full
    category: Core Rules

  # Pattern matching
  - pattern: https://www.d20pfsrd.com/magic/all-spells/*
    mode: template
    category: Spells
    name_prefix: Spell
    exclude_index_pages: true
```

#### Entry Fields

| Field | Description |
|-------|-------------|
| `url` | Single exact URL to match |
| `urls` | List of exact URLs to match |
| `pattern` | Glob pattern with `*` wildcard |
| `mode` | Processing mode (see below) |
| `category` | Category for search weight customization |
| `name` | Human-readable source name |
| `name_prefix` | Prefix prepended to page title (e.g., "Skill: Acrobatics") |
| `exclude` | URLs or patterns to exclude from pattern matches |
| `exclude_index_pages` | Auto-exclude single-char index pages (e.g., /a/, /b/) |

#### Processing Modes

| Mode | Description | LLM Required |
|------|-------------|--------------|
| `full` | Multiple sections extracted by LLM | Yes |
| `simple` | Single section with LLM summary | Yes |
| `template` | Template-based extraction (spells, feats) | No |
| `faq` | Q&A pair extraction from FAQ pages | No |
| `class` | Class feature extraction with TOC | Yes |

#### Exclude Patterns

Excludes can be specified as:

1. **Full URLs** - Exact match:
   ```yaml
   exclude:
     - https://www.d20pfsrd.com/feats/combat-feats/
   ```

2. **Relative patterns** - Match URL suffixes using `*/` prefix:
   ```yaml
   exclude:
     - "*/paizo-alchemist-archetypes/"  # Matches any URL ending with this
   ```

3. **Auto-generated** - Use `exclude_index_pages: true` to auto-exclude:
   - Single-character path segments (e.g., `/all-spells/a/`, `/all-spells/b/`)
   - The base URL of the pattern (without wildcard)

## Example: Complete Entry

```yaml
- pattern: https://www.d20pfsrd.com/skills/*
  mode: simple
  category: Skills
  name_prefix: Skill
  exclude:
    - https://www.d20pfsrd.com/skills/  # Base index page
    - https://www.d20pfsrd.com/skills/background-skills/
    - "*/skills-from-other-publishers/"  # 3rd party content
```
