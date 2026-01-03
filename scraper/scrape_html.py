#!/usr/bin/env python3
"""
Scrape and store HTML content from d20pfsrd.com URLs.

Usage:
    poetry run python scrape_html.py                    # Scrape all filtered URLs
    poetry run python scrape_html.py -i urls.txt        # Scrape from specific file
    poetry run python scrape_html.py --workers 5        # Use 5 parallel workers
    poetry run python scrape_html.py --get URL          # Get stored HTML for a URL
    poetry run python scrape_html.py --stats            # Show database stats
    poetry run python scrape_html.py --sample 5         # Show 5 random stored URLs
"""

import argparse
import random
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from urllib.parse import urlparse

import requests

DB_PATH = Path("html_cache.db")
DEFAULT_INPUT = "filtered_urls.txt"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Rate limiting: respect robots.txt crawl-delay of 10s, but we can be slightly faster
# with multiple workers since each worker handles different URLs
REQUEST_TIMEOUT = 30
MIN_DELAY_BETWEEN_REQUESTS = 1.0  # seconds per worker


class HtmlCache:
    """SQLite-backed cache for HTML content."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()
        self._lock = Lock()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS html_cache (
                    url TEXT PRIMARY KEY,
                    html TEXT,
                    status_code INTEGER,
                    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    error TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON html_cache(status_code)")

    def get(self, url: str) -> dict | None:
        """Get cached HTML for a URL."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT url, html, status_code, fetched_at, error FROM html_cache WHERE url = ?",
                (url,)
            ).fetchone()
            if row:
                return dict(row)
            return None

    def put(self, url: str, html: str | None, status_code: int, error: str | None = None):
        """Store HTML for a URL."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO html_cache (url, html, status_code, error, fetched_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (url, html, status_code, error))

    def has(self, url: str) -> bool:
        """Check if URL is already cached."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM html_cache WHERE url = ?", (url,)
            ).fetchone()
            return row is not None

    def get_cached_urls(self) -> set[str]:
        """Get all cached URLs."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT url FROM html_cache").fetchall()
            return {row[0] for row in rows}

    def stats(self) -> dict:
        """Get cache statistics."""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM html_cache").fetchone()[0]
            success = conn.execute(
                "SELECT COUNT(*) FROM html_cache WHERE status_code = 200"
            ).fetchone()[0]
            errors = conn.execute(
                "SELECT COUNT(*) FROM html_cache WHERE error IS NOT NULL"
            ).fetchone()[0]
            return {"total": total, "success": success, "errors": errors}

    def sample(self, n: int = 5) -> list[str]:
        """Get n random cached URLs."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT url FROM html_cache WHERE status_code = 200 ORDER BY RANDOM() LIMIT ?",
                (n,)
            ).fetchall()
            return [row[0] for row in rows]


def fetch_url(url: str, cache: HtmlCache) -> tuple[str, bool, str]:
    """
    Fetch a URL and cache it. Returns (url, success, message).
    """
    if cache.has(url):
        return (url, True, "cached")

    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        cache.put(url, response.text, response.status_code)
        time.sleep(MIN_DELAY_BETWEEN_REQUESTS)
        return (url, True, f"fetched ({response.status_code})")
    except requests.exceptions.Timeout:
        cache.put(url, None, 0, error="timeout")
        return (url, False, "timeout")
    except requests.exceptions.RequestException as e:
        cache.put(url, None, 0, error=str(e))
        return (url, False, f"error: {e}")


def scrape_urls(urls: list[str], cache: HtmlCache, workers: int = 3):
    """Scrape URLs in parallel with progress tracking."""
    # Filter out already cached URLs
    cached = cache.get_cached_urls()
    to_fetch = [u for u in urls if u not in cached]

    print(f"Total URLs: {len(urls)}")
    print(f"Already cached: {len(cached)}")
    print(f"To fetch: {len(to_fetch)}")

    if not to_fetch:
        print("Nothing to fetch!")
        return

    print(f"\nStarting scrape with {workers} workers...")
    completed = 0
    errors = 0
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_url, url, cache): url for url in to_fetch}

        for future in as_completed(futures):
            url, success, message = future.result()
            completed += 1
            if not success:
                errors += 1

            # Progress update every 100 URLs or on error
            if completed % 100 == 0 or not success:
                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 0
                remaining = len(to_fetch) - completed
                eta = remaining / rate if rate > 0 else 0
                print(
                    f"Progress: {completed}/{len(to_fetch)} "
                    f"({errors} errors) - {rate:.1f}/s - ETA: {eta/60:.1f}min"
                )

    elapsed = time.time() - start_time
    print(f"\nDone! Fetched {completed} URLs in {elapsed/60:.1f} minutes ({errors} errors)")


def main():
    parser = argparse.ArgumentParser(description="Scrape and cache HTML from d20pfsrd.com")
    parser.add_argument("-i", "--input", default=DEFAULT_INPUT,
                        help=f"Input file with URLs (default: {DEFAULT_INPUT})")
    parser.add_argument("--workers", type=int, default=3,
                        help="Number of parallel workers (default: 3)")
    parser.add_argument("--get", metavar="URL",
                        help="Get cached HTML for a specific URL")
    parser.add_argument("--stats", action="store_true",
                        help="Show cache statistics")
    parser.add_argument("--sample", type=int, metavar="N",
                        help="Show N random cached URLs")
    args = parser.parse_args()

    cache = HtmlCache()

    if args.get:
        result = cache.get(args.get)
        if result:
            print(f"URL: {result['url']}")
            print(f"Status: {result['status_code']}")
            print(f"Fetched: {result['fetched_at']}")
            if result['error']:
                print(f"Error: {result['error']}")
            else:
                print(f"HTML length: {len(result['html'])} chars")
                print("\n--- HTML Content ---\n")
                print(result['html'])
        else:
            print(f"URL not in cache: {args.get}")
        return

    if args.stats:
        stats = cache.stats()
        print(f"Cache statistics:")
        print(f"  Total URLs: {stats['total']}")
        print(f"  Successful: {stats['success']}")
        print(f"  Errors: {stats['errors']}")
        return

    if args.sample:
        urls = cache.sample(args.sample)
        print(f"Random cached URLs ({len(urls)}):")
        for url in urls:
            print(f"  {url}")
        return

    # Load URLs and scrape
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        return

    urls = input_path.read_text().strip().split("\n")
    scrape_urls(urls, cache, workers=args.workers)


if __name__ == "__main__":
    main()
