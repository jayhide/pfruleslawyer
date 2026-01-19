# Extraction Module

Section extraction from manifest files.

## Files

- `extractor.py` - `SectionExtractor` class for loading and searching sections

## Key Class

### SectionExtractor
Loads section manifests from `data/manifests/` and extracts content from markdown.

```python
extractor = SectionExtractor()
sections = extractor.load_all_sections()  # Returns list of Section objects

# Search by text (matches title, description, keywords)
results = extractor.search_by_text("grapple")

# Get specific section by ID
section = extractor.get_section_by_id("flat_footed_condition")
```

## How It Works

1. Loads JSON manifest files from `data/manifests/`
2. For each section in a manifest:
   - Fetches markdown from database (if source is URL) or file
   - Extracts content between anchor headings
   - Returns populated `Section` objects
