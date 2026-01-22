# Core Module

Domain models and data access layer.

## Files

- `section.py` - `Section` dataclass representing a rules section with id, title, description, keywords, content, source info
- `db.py` - `HtmlCacheDB` class for read-only access to the scraper's SQLite database
- `timing.py` - Timing utilities for instrumenting operations

## Key Classes

### Section
```python
@dataclass
class Section:
    id: str
    title: str
    description: str
    keywords: list[str]
    content: str
    source_file: str
    source_name: str
    anchor_heading: str
    category: str = "Uncategorized"
```

### HtmlCacheDB
Singleton class for querying `scraper/html_cache.db`:
- `get_markdown(url)` - Get markdown for a URL
- `get_html(url)` - Get raw HTML for a URL
- `get_all_urls_with_markdown()` - List all URLs with content
- `has_url(url)` - Check if URL exists
- `stats()` - Get database statistics

### TimingContext
Accumulates timing data across multiple operations:
```python
ctx = TimingContext()
with ctx.measure("operation_name"):
    # do work
ctx.record("manual_timing", duration_ms)
print(ctx.summary())  # Formatted timing report
ctx.as_dict()  # JSON-serializable dict
```

### optional_timing
Helper that returns `ctx.measure()` if ctx is provided, else a no-op:
```python
with optional_timing(ctx, "operation"):
    # do work (timed only if ctx is not None)
```
