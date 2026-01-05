# Scraper

Scripts for discovering URLs from d20pfsrd.com, scraping HTML, and converting to markdown.

## URL Discovery

### Fetching URLs from Sitemap

```bash
# Fetch all page URLs from sitemap
poetry run python scraper/fetch_sitemap_urls.py --pages-only

# Include taxonomy sitemaps
poetry run python scraper/fetch_sitemap_urls.py

# Also crawl category pages for additional discovery
poetry run python scraper/fetch_sitemap_urls.py --crawl
```

Output: `sitemap_urls.txt` with all discovered URLs.

Note: The d20pfsrd server returns HTTP 404 status codes but still serves valid sitemap XML content. The script handles this by parsing response content regardless of status code.

### Filtering URLs

```bash
# Show what would be filtered (dry run)
poetry run python scraper/filter_urls.py --stats

# Filter and save
poetry run python scraper/filter_urls.py -i scraper/sitemap_urls.txt -o scraper/filtered_urls.txt
```

Current exclusion patterns:
- `/3rd-party`, `3pp-` - Third-party publisher content
- `/extras/` - Community creations, review queues
- `/work-area/` - Internal work pages
- `/alternative-rule-systems/` - Mixed first/third-party, excluded for now
- `/subscribe/`, `/gaming-accessories/`, `/d20pfsrd-com-publishing-products/` - Non-rules content
- Third-party archetypes detected by checking for `paizo` in archetype folder paths

## HTML Scraping

```bash
# Scrape all filtered URLs (stores in html_cache.db)
poetry run python scraper/scrape_html.py

# Use more workers for faster scraping
poetry run python scraper/scrape_html.py --workers 5

# Check progress
poetry run python scraper/scrape_html.py --stats

# Retrieve cached HTML for a specific URL
poetry run python scraper/scrape_html.py --get "https://www.d20pfsrd.com/feats/combat-feats/power-attack-combat/"
```

## Markdown Conversion

Convert cached HTML to clean markdown:

```bash
# Convert all cached HTML to markdown
poetry run python scraper/convert_to_markdown.py

# Get markdown for a specific URL
poetry run python scraper/convert_to_markdown.py --get "https://www.d20pfsrd.com/feats/combat-feats/power-attack-combat/"

# Preview conversion without saving
poetry run python scraper/convert_to_markdown.py --preview URL

# Check conversion stats
poetry run python scraper/convert_to_markdown.py --stats

# Force re-convert all pages
poetry run python scraper/convert_to_markdown.py --force
```

Content extraction:
- Starts at first `<h1>` tag
- Stops at copyright section (`div.section15`) or sidebar fallback (`div.right-sidebar`, etc.)
- Preserves links (useful for LLM context)
- Use `strip_links(markdown)` when generating embeddings to avoid confusing semantic search

Programmatic usage:
```python
from scraper.convert_to_markdown import MarkdownCache, strip_links

cache = MarkdownCache()
markdown = cache.get_markdown("https://www.d20pfsrd.com/...")

# For embeddings, strip links
text_for_embedding = strip_links(markdown)
```

## HTML Analysis

Analyze cached HTML to test content extraction heuristics:

```bash
# Analyze all cached pages
poetry run python scraper/analyze_html.py

# Show pages missing h1 tags or copyright sections
poetry run python scraper/analyze_html.py --show-missing-h1
poetry run python scraper/analyze_html.py --show-missing-copyright

# Show pages with very short content
poetry run python scraper/analyze_html.py --show-short 200

# Show pages with multiple h1 tags
poetry run python scraper/analyze_html.py --show-multi-h1
```

Reports statistics on:
- H1 tag presence (starting point for content extraction)
- Copyright section presence (ending point for content extraction)
- Content length distribution when converted to markdown

## URL Analysis

Analyze URL path hierarchy to understand content distribution:

```bash
# Tree view with counts
poetry run python scraper/analyze_urls.py

# Limit depth and minimum count
poetry run python scraper/analyze_urls.py --max-depth 2 --min-count 10

# Flat view sorted by count
poetry run python scraper/analyze_urls.py --flat --sort-by-count

# Analyze a URL file instead of database
poetry run python scraper/analyze_urls.py -i scraper/filtered_urls.txt
```
