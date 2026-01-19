"""Core domain models and data access."""

from .db import HtmlCacheDB, get_db, search_urls
from .section import Section

__all__ = ["HtmlCacheDB", "get_db", "search_urls", "Section"]
