# PF Rules Lawyer

A RAG-powered Pathfinder 1st Edition rules assistant that uses semantic search over scraped rules content to answer rules questions.

## Features

- **Semantic Search**: Vector-based search over ~5,300 rules sections using ChromaDB
- **Cross-encoder Reranking**: Improves search result relevance
- **Agentic Q&A**: Claude can issue follow-up searches and follow links in rules text
- **Category-specific Weights**: Different search strategies for spells, feats, core rules, etc.

## Installation

```bash
# Install dependencies
poetry install

# Download spaCy language model
poetry run python -m spacy download en_core_web_sm
```

## Usage

```bash
# Ask a rules question
poetry run pfrules "How does grappling work?"

# Interactive mode
poetry run pfrules

# Build/rebuild the search index
poetry run pfrules-vectordb --build

# Query the index directly
poetry run pfrules-vectordb -q "attack of opportunity"
```

## Requirements

- Python 3.10+
- `ANTHROPIC_API_KEY` environment variable (in `.env` file)

## License

Private/Internal Use
