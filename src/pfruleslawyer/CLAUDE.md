# pfruleslawyer Package

Main Python package for the Pathfinder 1e Rules Lawyer application.

## Submodules

- `core/` - Domain models and data access (Section dataclass, HtmlCacheDB)
- `extraction/` - Section extraction from manifests (SectionExtractor)
- `modification/` - Markdown content modification before preprocessing
- `preprocessing/` - LLM-powered section extraction and manifest generation
- `search/` - Vector search, lemmatization, and reranking
- `rag/` - RAG-powered Q&A logic
- `web/` - Future Flask web application (placeholder)

## Usage

```python
# Import from submodules
from pfruleslawyer.core import Section, HtmlCacheDB
from pfruleslawyer.extraction import SectionExtractor
from pfruleslawyer.modification import MarkdownModifier
from pfruleslawyer.search import RulesVectorStore
from pfruleslawyer.rag import ask_rules_question
```
