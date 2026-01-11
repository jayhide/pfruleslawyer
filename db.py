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


def search_urls(db: HtmlCacheDB, pattern: str) -> list[str]:
    """Search for URLs matching a pattern.

    Args:
        db: Database instance
        pattern: SQL LIKE pattern (use % for wildcards)

    Returns:
        List of matching URLs
    """
    conn = db._connect()
    try:
        cursor = conn.execute(
            "SELECT url FROM html_cache WHERE url LIKE ? ORDER BY url",
            (pattern,)
        )
        return [row[0] for row in cursor.fetchall()]
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


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Query the html_cache.db database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s stats                          Show database statistics
  %(prog)s get URL                        Get markdown for a URL
  %(prog)s html URL                       Get raw HTML for a URL
  %(prog)s has URL                        Check if URL exists
  %(prog)s list                           List all URLs with markdown
  %(prog)s search 'feats/combat%%'        Search URLs (SQL LIKE pattern)
""",
    )
    parser.add_argument(
        "--db", type=Path, help="Path to database (default: scraper/html_cache.db)"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # stats
    subparsers.add_parser("stats", help="Show database statistics")

    # get (markdown)
    get_parser = subparsers.add_parser("get", help="Get markdown for a URL")
    get_parser.add_argument("url", help="URL to look up")

    # html
    html_parser = subparsers.add_parser("html", help="Get raw HTML for a URL")
    html_parser.add_argument("url", help="URL to look up")

    # has
    has_parser = subparsers.add_parser("has", help="Check if URL exists in cache")
    has_parser.add_argument("url", help="URL to check")

    # list
    list_parser = subparsers.add_parser("list", help="List all URLs with markdown")
    list_parser.add_argument(
        "-n", type=int, help="Limit number of results"
    )

    # search
    search_parser = subparsers.add_parser(
        "search", help="Search URLs with SQL LIKE pattern"
    )
    search_parser.add_argument(
        "pattern", help="SQL LIKE pattern (use %% for wildcards)"
    )
    search_parser.add_argument(
        "-n", type=int, help="Limit number of results"
    )

    args = parser.parse_args()
    db = HtmlCacheDB(args.db)

    if args.command == "stats":
        s = db.stats()
        print(f"Total URLs:      {s['total']:,}")
        print(f"With HTML:       {s['with_html']:,}")
        print(f"With Markdown:   {s['with_markdown']:,}")
        print(f"Errors:          {s['errors']:,}")

    elif args.command == "get":
        markdown = db.get_markdown(args.url)
        if markdown:
            print(markdown)
        else:
            print(f"No markdown found for: {args.url}", file=__import__("sys").stderr)
            raise SystemExit(1)

    elif args.command == "html":
        html = db.get_html(args.url)
        if html:
            print(html)
        else:
            print(f"No HTML found for: {args.url}", file=__import__("sys").stderr)
            raise SystemExit(1)

    elif args.command == "has":
        exists = db.has_url(args.url)
        print("yes" if exists else "no")
        raise SystemExit(0 if exists else 1)

    elif args.command == "list":
        urls = db.get_all_urls_with_markdown()
        if args.n:
            urls = urls[: args.n]
        for url in urls:
            print(url)

    elif args.command == "search":
        urls = search_urls(db, args.pattern)
        if args.n:
            urls = urls[: args.n]
        for url in urls:
            print(url)
        if not urls:
            print(f"No URLs matching: {args.pattern}", file=__import__("sys").stderr)


if __name__ == "__main__":
    main()
