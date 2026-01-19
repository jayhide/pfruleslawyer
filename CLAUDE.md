This is a repo that serves two purposes:
1) To scrape pathfinder 1e rules and content from the https://www.d20pfsrd.com/ website
2) To use RAG over the scraped rules to provide relevant context to an llm which answers questions on pathfinder 1e rules

poetry is used to track dependencies and maintain the environment for running code

## Project Structure

```
pfruleslawyer/
├── src/pfruleslawyer/           # Main installable package
│   ├── core/                    # Domain models & data access
│   │   ├── db.py                # HtmlCacheDB database access
│   │   └── section.py           # Section dataclass
│   ├── extraction/              # Section extraction
│   │   └── extractor.py         # SectionExtractor class
│   ├── preprocessing/           # LLM-powered preprocessing
│   │   ├── prompts.py           # Prompt templates
│   │   ├── processor.py         # Processing functions
│   │   └── from_db.py           # Config-driven processing
│   ├── search/                  # Vector search & retrieval
│   │   ├── vector_store.py      # RulesVectorStore
│   │   ├── lemmatizer.py        # Lemmatizer singleton
│   │   └── reranker.py          # Reranker singleton
│   ├── rag/                     # RAG application logic
│   │   └── rules_lawyer.py      # Q&A logic
│   └── web/                     # Future Flask web app (placeholder)
│
├── cli/                         # CLI entry points
│   ├── ask.py                   # rules_lawyer CLI
│   ├── preprocess.py            # preprocessing CLI
│   ├── vectordb.py              # vector store management CLI
│   └── db.py                    # database query CLI
│
├── scraper/                     # Standalone scraping pipeline
│   ├── fetch_sitemap_urls.py
│   ├── filter_urls.py
│   ├── scrape_html.py
│   ├── convert_to_markdown.py
│   ├── analyze_html.py
│   ├── analyze_urls.py
│   └── html_cache.db            # SQLite database
│
├── config/                      # Configuration files
│   ├── preprocess_config.json
│   └── class_secondary_urls.json
│
├── data/                        # Generated/runtime data
│   ├── manifests/               # Section manifests (JSON)
│   └── vectordb/                # ChromaDB + metadata_only.json
│
├── tests/                       # Test suite
│   ├── unit/                    # Unit tests
│   └── integration/             # Integration tests
│
├── tools/                       # Standalone utility scripts
│   └── spell_sorting/           # Spell list comparison utility
│
└── rules/                       # Legacy scraped markdown files
```

## Installation

```bash
# Install the package in development mode
poetry install

# Install spaCy language model
poetry run python -m spacy download en_core_web_sm
```

## CLI Commands

After installation, the following CLI commands are available:

```bash
# Ask rules questions (main interface)
poetry run pfrules "How does grappling work?"
poetry run pfrules "What is flat-footed?" -v
poetry run pfrules  # interactive mode

# Manage vector store
poetry run pfrules-vectordb --build       # Build/rebuild index
poetry run pfrules-vectordb -q "grapple"  # Query the index
poetry run pfrules-vectordb               # Show stats

# Preprocess markdown from database
poetry run pfrules-preprocess --stats     # Show what would be processed
poetry run pfrules-preprocess --dry-run   # Preview without API calls
poetry run pfrules-preprocess -v          # Process all configured URLs

# Query the HTML cache database
poetry run pfrules-db stats               # Show database statistics
poetry run pfrules-db get URL             # Get markdown for a URL
poetry run pfrules-db list                # List all URLs with markdown
```

## Section Preprocessing

The markdown files have inconsistent heading structures, so we use an LLM to identify logical sections for RAG retrieval.

### From Database

Process markdown directly from the scraper database using `config/preprocess_config.json`:

```bash
# Show what would be processed
poetry run pfrules-preprocess --stats

# Preview without API calls
poetry run pfrules-preprocess --dry-run -v

# Process all configured URLs
poetry run pfrules-preprocess -v

# Process specific category only
poetry run pfrules-preprocess --category "Combat Feats" -v

# Force reprocess existing manifests
poetry run pfrules-preprocess --force
```

### Configuration Format

Edit `config/preprocess_config.json` to specify URLs to process:

```json
{
  "entries": [
    {
      "url": "https://www.d20pfsrd.com/gamemastering/combat/",
      "mode": "full",
      "category": "Core Rules",
      "name": "Combat Rules"
    },
    {
      "pattern": "https://www.d20pfsrd.com/feats/combat-feats/*",
      "mode": "simple",
      "category": "Combat Feats",
      "name": "Feat: Combat",
      "exclude": ["https://www.d20pfsrd.com/feats/combat-feats/some-bad-feat/"]
    }
  ]
}
```

- `url` - Exact URL match
- `urls` - List of exact URL matches
- `pattern` - Glob pattern (supports `*` wildcard)
- `mode` - `"full"` (multiple sections), `"simple"` (single section), or `"template"` (no LLM)
- `category` - Human-readable name for filtering and search weight customization
- `name` - (optional) Source name for manifests (overrides auto-generated name)
- `name_prefix` - (optional) Prefix for source name, combined with page title (e.g., `"Skill"` → "Skill: Acrobatics")
- `exclude` - (optional) URLs to skip within a pattern

### Category Weights

Categories can have custom search weights defined in `config/preprocess_config.json`:

```json
{
  "category_weights": {
    "_default": {
      "semantic_weight": 1.0,
      "keyword_boost": 0.2,
      "subheading_boost": 0.2,
      "title_boost": 0.3,
      "rerank_weight": 0.4
    },
    "Spells": {
      "semantic_weight": 0.0,
      "title_boost": 1.0,
      "rerank_weight": 0.2
    },
    "Archetypes": {
      "semantic_weight": 0.0,
      "title_boost": 1.0,
      "rerank_weight": 0.2
    }
  }
}
```

Categories with `semantic_weight: 0` (like Spells and Archetypes) use **title-only matching**:
- They are NOT embedded in ChromaDB (saves indexing time and storage)
- They are stored as metadata-only in `data/vectordb/metadata_only.json`
- Queries only match them when the title matches (e.g., "fireball" matches Fireball spell)
- This prevents retrieving a wizard archetype just because "wizard" was mentioned

### Output Format

Each manifest in `data/manifests/` contains sections with:
- `id` - Unique identifier
- `title` - Human-readable name
- `anchor_heading` - Exact markdown heading to locate the section
- `description` - Brief summary of the rules covered
- `keywords` - Terms for retrieval matching

## Section Extraction

Use `SectionExtractor` to load and search sections:

```python
from pfruleslawyer.extraction import SectionExtractor

extractor = SectionExtractor()
sections = extractor.load_all_sections()  # ~5,300 sections

# Search by text (matches title, description, keywords)
results = extractor.search_by_text("grapple")

# Get specific section by ID
section = extractor.get_section_by_id("flat_footed_condition")
print(section.content)  # Full markdown content
```

Each `Section` object has: `id`, `title`, `description`, `keywords`, `content`, `source_file`, `anchor_heading`

## Vector Search (RAG)

Build and query the semantic search index:

```bash
# Build/rebuild the index
poetry run pfrules-vectordb --build

# Query for relevant sections
poetry run pfrules-vectordb -q "how does grappling work"
poetry run pfrules-vectordb -q "attack of opportunity" -n 10
```

The index splits sections into two storage types based on category weights:
- **Semantic sections** (~1,400): Embedded in ChromaDB for semantic similarity search
- **Metadata-only sections** (~3,800): Stored in JSON for title/keyword matching only

This optimization reduces index build time and improves query performance for categories like Spells and Archetypes that use title-only matching.

Or use programmatically:

```python
from pfruleslawyer.search import RulesVectorStore

store = RulesVectorStore()
results = store.query("what happens when I fall unconscious", n_results=5)

for r in results:
    print(f"{r['title']} (score: {r['score']:.3f})")
    print(r['content'])
```

### Link Resolution

The vector store supports following links with URL fragments (e.g., `#spell_combat_ex`). Anchor IDs are extracted directly from markdown headings like `#### Spell Combat (Ex) {#spell_combat_ex}` and indexed for lookup:

```python
from pfruleslawyer.search import RulesVectorStore

store = RulesVectorStore()
result = store.resolve_link("https://www.d20pfsrd.com/classes/base-classes/magus#spell_combat_ex")
print(result["content"])  # Returns section containing the anchor
```

## Asking Rules Questions

The main interface for asking Pathfinder rules questions:

```bash
# Single question
poetry run pfrules "How does grappling work?"

# With verbose output (shows retrieved sections)
poetry run pfrules "What is flat-footed?" -v

# Interactive mode
poetry run pfrules
```

The system retrieves the top relevant rules sections and uses Claude to answer based on those rules.

## Scraper

The `scraper/` directory contains scripts for discovering URLs, scraping HTML, and converting to markdown. See `scraper/CLAUDE.md` for detailed usage.

Key scripts:
- `scraper/fetch_sitemap_urls.py` - Discover URLs from sitemap
- `scraper/filter_urls.py` - Filter out third-party content
- `scraper/scrape_html.py` - Scrape and cache HTML
- `scraper/convert_to_markdown.py` - Convert HTML to markdown
- `scraper/analyze_html.py` - Analyze cached HTML
- `scraper/analyze_urls.py` - Analyze URL path hierarchy with counts

## Database Access

The `pfruleslawyer.core.db` module provides unified read-only access to `scraper/html_cache.db`:

```python
from pfruleslawyer.core import HtmlCacheDB

db = HtmlCacheDB()

# Get markdown for a URL
markdown = db.get_markdown("https://www.d20pfsrd.com/classes/core-classes/fighter/")

# Get all URLs with markdown content
urls = db.get_all_urls_with_markdown()

# Get raw HTML
html = db.get_html("https://www.d20pfsrd.com/classes/core-classes/fighter/")

# Check if URL exists
exists = db.has_url("https://www.d20pfsrd.com/some-url/")

# Get statistics
stats = db.stats()  # {total, with_html, with_markdown, errors}
```

The `SectionExtractor` automatically uses this to fetch markdown when a manifest's `source_path` is a URL.

## Testing

Tests are organized into unit and integration tests:

```bash
poetry run pytest                              # run all tests
poetry run pytest -v                           # verbose output
poetry run pytest tests/unit/                  # unit tests only
poetry run pytest tests/integration/           # integration tests only
poetry run pytest tests/unit/test_preprocess_sections.py  # specific file
```

## Environment

Requires `ANTHROPIC_API_KEY` in `.env` file.
