"""Unified database access for html_cache.db."""

import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path("scraper/html_cache.db")


class HtmlCacheDB:
    """Read-only access to the HTML cache database.

    Provides methods to query cached HTML and markdown content by URL.
    """

    _instance: "HtmlCacheDB | None" = None
    _db_path: Path | None = None

    def __new__(cls, db_path: Path | None = None) -> "HtmlCacheDB":
        """Singleton pattern - reuse instance if same db_path."""
        path = db_path or DEFAULT_DB_PATH
        if cls._instance is None or cls._db_path != path:
            cls._instance = super().__new__(cls)
            cls._db_path = path
        return cls._instance

    def __init__(self, db_path: Path | None = None):
        """Initialize database connection.

        Args:
            db_path: Path to the SQLite database. Defaults to scraper/html_cache.db
        """
        self.db_path = db_path or DEFAULT_DB_PATH

    def _connect(self) -> sqlite3.Connection:
        """Create a database connection with proper text handling."""
        conn = sqlite3.connect(self.db_path)
        # Handle encoding issues gracefully
        conn.text_factory = lambda b: b.decode("utf-8", errors="replace")
        return conn

    def get_markdown(self, url: str) -> str | None:
        """Get markdown content for a specific URL.

        Args:
            url: The URL to look up

        Returns:
            Markdown content or None if not found
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT markdown FROM html_cache WHERE url = ?", (url,)
            )
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def get_html(self, url: str) -> str | None:
        """Get raw HTML content for a specific URL.

        Args:
            url: The URL to look up

        Returns:
            HTML content or None if not found
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT html FROM html_cache WHERE url = ? AND html IS NOT NULL",
                (url,)
            )
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def get_all_urls_with_markdown(self) -> list[str]:
        """Get all URLs that have markdown content.

        Returns:
            List of URLs with non-empty markdown
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT url FROM html_cache WHERE markdown IS NOT NULL AND markdown != ''"
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    def has_url(self, url: str) -> bool:
        """Check if a URL exists in the cache.

        Args:
            url: The URL to check

        Returns:
            True if URL exists in cache
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT 1 FROM html_cache WHERE url = ?", (url,)
            )
            return cursor.fetchone() is not None
        finally:
            conn.close()

    def stats(self) -> dict:
        """Get database statistics.

        Returns:
            Dictionary with counts for total, with_html, with_markdown, errors
        """
        conn = self._connect()
        try:
            total = conn.execute("SELECT COUNT(*) FROM html_cache").fetchone()[0]
            with_html = conn.execute(
                "SELECT COUNT(*) FROM html_cache WHERE html IS NOT NULL"
            ).fetchone()[0]
            with_markdown = conn.execute(
                "SELECT COUNT(*) FROM html_cache WHERE markdown IS NOT NULL AND markdown != ''"
            ).fetchone()[0]
            errors = conn.execute(
                "SELECT COUNT(*) FROM html_cache WHERE error IS NOT NULL"
            ).fetchone()[0]

            return {
                "total": total,
                "with_html": with_html,
                "with_markdown": with_markdown,
                "errors": errors
            }
        finally:
            conn.close()


# Module-level convenience function
def get_db(db_path: Path | None = None) -> HtmlCacheDB:
    """Get the database instance.

    Args:
        db_path: Optional path to database

    Returns:
        HtmlCacheDB singleton instance
    """
    return HtmlCacheDB(db_path)
