This is a repo that serves two purposes:
1) To scrape pathfinder 1e rules and content from the https://www.d20pfsrd.com/ website
2) To use RAG over the scraped rules to provide relevant context to an llm which answers questions on pathfinder 1e rules

## Development

poetry is used to track dependencies and maintain the environment for running code

Always update the relevant CLAUDE.md files when making significant changes to the codebase.

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
│   └── web/                     # FastAPI web server
│       ├── app.py               # FastAPI app with frontend serving
│       ├── models.py            # Request/response models
│       └── streaming.py         # SSE streaming logic
│
├── frontend/                    # React SPA frontend
│   ├── src/
│   │   ├── components/          # React components
│   │   ├── hooks/               # Custom hooks
│   │   ├── services/            # API service layer
│   │   └── types/               # TypeScript definitions
│   ├── vite.config.ts
│   └── package.json
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

**Prerequisites:**
- Python 3.10+
- Poetry
- Node.js 18+ (for frontend only)

```bash
# Install Python dependencies
poetry install

# Install spaCy language model
poetry run python -m spacy download en_core_web_sm
```

## Quick Start

```bash
poetry run pfrules "How does grappling work?"  # Ask a rules question
poetry run pfrules-vectordb --build            # Build search index
poetry run pfrules-preprocess -v               # Process markdown to manifests
poetry run pfrules-db stats                    # Database statistics
poetry run pfrules-server                      # Start web server
```

See `cli/CLAUDE.md` for full command documentation.

## Web Frontend

```bash
# Build frontend (requires Node.js)
cd frontend && npm install && npm run build

# Start server (serves frontend at http://localhost:8000)
poetry run pfrules-server
```

See `frontend/CLAUDE.md` for frontend development details.

## Key Components

**Scraping Pipeline** - Scripts in `scraper/` discover URLs, fetch HTML, and convert to markdown. See `scraper/CLAUDE.md`.

**Preprocessing** - LLM-powered section extraction from markdown into manifests. See `src/pfruleslawyer/preprocessing/CLAUDE.md` and `config/CLAUDE.md`.

**Vector Search** - Semantic search over rules using ChromaDB embeddings. See `src/pfruleslawyer/search/CLAUDE.md`.

**RAG Q&A** - Retrieval-augmented generation for answering rules questions. See `src/pfruleslawyer/rag/CLAUDE.md`.

## Module Documentation

Each directory contains its own CLAUDE.md with detailed documentation:

| Directory | Description |
|-----------|-------------|
| `src/pfruleslawyer/` | Main Python package |
| `src/pfruleslawyer/core/` | Domain models (Section, HtmlCacheDB) |
| `src/pfruleslawyer/extraction/` | SectionExtractor for loading sections |
| `src/pfruleslawyer/preprocessing/` | LLM processing modes and functions |
| `src/pfruleslawyer/search/` | Vector store, lemmatizer, reranker |
| `src/pfruleslawyer/rag/` | Q&A logic with tool use |
| `src/pfruleslawyer/web/` | FastAPI server and SSE streaming |
| `frontend/` | React SPA frontend |
| `cli/` | CLI entry points and commands |
| `config/` | Configuration file formats |
| `data/` | Generated manifests and vector index |
| `scraper/` | HTML scraping pipeline |
| `tests/` | Test suite structure |
| `tools/` | Standalone utility scripts |

## Testing

```bash
poetry run pytest                    # All tests
poetry run pytest tests/unit/        # Fast unit tests
poetry run pytest tests/integration/ # Tests requiring index
```

See `tests/CLAUDE.md` for test organization details.

## Environment

Requires `ANTHROPIC_API_KEY` in `.env` file.
