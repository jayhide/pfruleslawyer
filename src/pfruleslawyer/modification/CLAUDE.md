# Modification Module

Configuration-driven markdown modification layer that transforms content before preprocessing.

## Architecture

```
Database (original) → MarkdownModifier → Preprocessing/Extraction (modified)
```

The modification layer wraps `db.get_markdown()` calls, applying transformations while keeping the original database content unchanged.

## Files

- `modifier.py` - `MarkdownModifier` class that loads config and applies operations
- `operations.py` - Individual operation functions (remove_section, remove_lines, etc.)

## Usage

```python
from pfruleslawyer.modification import MarkdownModifier
from pfruleslawyer.core import HtmlCacheDB

db = HtmlCacheDB()
modifier = MarkdownModifier()  # Loads from config/preprocess_config.yaml

# Get modified markdown
markdown = modifier.get_markdown(db, url)

# Preview changes
original, modified, changes = modifier.preview(db, url)
for change in changes:
    print(change)

# Check if URL has modifications
if modifier.has_modifications(url):
    print("URL has configured modifications")

# List all configured modifications
for entry in modifier.get_all_modified_urls():
    print(entry)
```

## Supported Operations

| Operation | Description | Parameters |
|-----------|-------------|------------|
| `remove_section` | Remove content between headings | `start_heading`, `end_heading` (optional) |
| `remove_lines` | Remove lines matching regex | `pattern` |
| `remove_text` | Remove exact text | `text` |
| `replace` | Regex find-and-replace | `pattern`, `replacement` |

### remove_section

Removes all content from `start_heading` until:
- `end_heading` if specified (the end heading itself is NOT removed), OR
- The next heading at the same or higher level

```yaml
- type: remove_section
  start_heading: "## Third-Party Options"
  end_heading: "## Official Content"  # optional
```

### remove_lines

Removes all lines matching a regex pattern.

```yaml
- type: remove_lines
  pattern: "\\*\\*Source\\*\\*.*3pp.*"
```

### remove_text

Removes exact text occurrences.

```yaml
- type: remove_text
  text: "[Show][Hide]"
```

### replace

Regex find-and-replace. Supports backreferences.

```yaml
- type: replace
  pattern: "\\[Show\\].*?\\[Hide\\]"
  replacement: ""
```

## Configuration

Add to `config/preprocess_config.yaml`:

```yaml
markdown_modifications:
  # Exact URL match
  - url: https://www.d20pfsrd.com/gamemastering/combat/
    operations:
      - type: remove_section
        start_heading: "## Third-Party Options"

  # Pattern-based (applies to multiple URLs)
  - pattern: https://www.d20pfsrd.com/feats/*/*
    operations:
      - type: remove_section
        start_heading: "## Mythic Version"
```

## CLI Commands

```bash
# Preview modifications for a URL (shows diff)
poetry run pfrules-preprocess --preview-modifications URL

# List all URLs with configured modifications
poetry run pfrules-preprocess --list-modifications
```
