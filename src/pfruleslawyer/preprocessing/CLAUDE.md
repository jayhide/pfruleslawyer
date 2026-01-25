# Preprocessing Module

LLM-powered section extraction and manifest generation.

## Files

- `prompts.py` - Prompt templates for LLM-based section extraction
- `processor.py` - Processing functions for different content types
- `from_db.py` - Config-driven batch processing from database

## Processing Modes

| Mode | Description | LLM Required |
|------|-------------|--------------|
| `full` | Multiple sections extracted by LLM | Yes |
| `simple` | Single section with LLM summary | Yes |
| `template` | Template-based extraction (spells, feats) | No |
| `faq` | Q&A pair extraction from FAQ pages | No |
| `class` | Class feature extraction with TOC | Yes |

## Key Functions

### processor.py
- `process_markdown_full()` - Full LLM extraction
- `process_markdown_simple()` - Single section with summary
- `process_markdown_template()` - No-LLM template processing
- `process_markdown_faq()` - FAQ Q&A extraction
- `process_markdown_class()` - Class document processing
- `get_source_name()` - Generate human-readable source names

### from_db.py
- `load_config()` - Load config from YAML file
- `process_url()` - Process single URL to manifest
- `get_urls_to_process()` - Resolve URLs from config patterns
- `is_index_page()` - Check if URL is an index page for auto-exclusion
- `matches_relative_exclude()` - Check if URL matches a relative exclude pattern

## Configuration

See `config/preprocess_config.yaml` for URL patterns, modes, and category weights.
