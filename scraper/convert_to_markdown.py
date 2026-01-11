#!/usr/bin/env python3
"""
Convert cached HTML to clean markdown.

Usage:
    poetry run python convert_to_markdown.py              # Convert all cached HTML
    poetry run python convert_to_markdown.py --get URL    # Get markdown for a URL
    poetry run python convert_to_markdown.py --preview URL # Preview without saving
    poetry run python convert_to_markdown.py --stats      # Show conversion stats
"""

import argparse
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

from bs4 import BeautifulSoup
from markdownify import markdownify as md, MarkdownConverter

DB_PATH = Path("html_cache.db")


def log(msg: str):
    """Print with immediate flush for real-time logging."""
    print(msg, flush=True)


def strip_links(markdown: str) -> str:
    """
    Remove markdown links, keeping only the link text.
    Use this for embeddings/semantic search to avoid confusing the model.

    Example: [Power Attack](https://...) -> Power Attack
    """
    pattern = r'\[([^\]]+)\]\([^)]+\)'
    return re.sub(pattern, r'\1', markdown)


class AnchorPreservingConverter(MarkdownConverter):
    """Custom markdown converter that preserves HTML anchor IDs in headings.

    Converts headings to extended markdown syntax with anchor IDs:
        <h4><span id="spell_combat_ex">Spell Combat (Ex)</span></h4>
    becomes:
        #### Spell Combat (Ex) {#spell_combat_ex}

    This enables direct fragment-based lookup in the RAG system.
    """

    def _extract_anchor_id(self, el) -> str | None:
        """Extract anchor ID from heading element.

        Priority:
        1. <span id="anchor_id"> inside heading (most common on d20pfsrd)
        2. id attribute directly on heading element

        Returns None if no suitable anchor found.
        """
        # Pattern 1: span with id inside the heading
        span = el.find('span', id=True)
        if span:
            anchor_id = span.get('id')
            # Skip UI-related IDs
            if anchor_id and not anchor_id.startswith('expand-'):
                return anchor_id

        # Pattern 2: id directly on heading element (skip TOC- prefixed)
        h_id = el.get('id')
        if h_id and not h_id.upper().startswith('TOC-'):
            return h_id

        return None

    def convert_hn(self, n, el, text, parent_tags):
        """Convert heading with anchor ID preservation.

        Overrides base class to append {#anchor_id} when available.
        """
        if '_inline' in parent_tags:
            return text

        # Constrain heading level
        n = max(1, min(6, n))
        style = self.options.get('heading_style', 'ATX').lower()
        text = text.strip()

        if not text:
            return ''

        # Clean whitespace
        text = re.sub(r'\s+', ' ', text)

        # For underlined style with n <= 2, no anchor support
        if style == 'underlined' and n <= 2:
            line = '=' if n == 1 else '-'
            return self.underline(text, line)

        hashes = '#' * n

        # Extract anchor ID
        anchor_id = self._extract_anchor_id(el)

        if style == 'atx_closed':
            if anchor_id:
                return '\n\n%s %s {#%s} %s\n\n' % (hashes, text, anchor_id, hashes)
            return '\n\n%s %s %s\n\n' % (hashes, text, hashes)

        # ATX style (default)
        if anchor_id:
            return '\n\n%s %s {#%s}\n\n' % (hashes, text, anchor_id)
        return '\n\n%s %s\n\n' % (hashes, text)

    # Override individual heading methods to use convert_hn
    def convert_h1(self, el, text, parent_tags):
        return self.convert_hn(1, el, text, parent_tags)

    def convert_h2(self, el, text, parent_tags):
        return self.convert_hn(2, el, text, parent_tags)

    def convert_h3(self, el, text, parent_tags):
        return self.convert_hn(3, el, text, parent_tags)

    def convert_h4(self, el, text, parent_tags):
        return self.convert_hn(4, el, text, parent_tags)

    def convert_h5(self, el, text, parent_tags):
        return self.convert_hn(5, el, text, parent_tags)

    def convert_h6(self, el, text, parent_tags):
        return self.convert_hn(6, el, text, parent_tags)


def find_content_end(soup: BeautifulSoup, first_h1) -> tuple[bool, any]:
    """
    Find where content ends. Returns (found_end_marker, end_element).

    Priority:
    1. Copyright section (div.section15 or "Section 15" text)
    2. Fallback: right-sidebar, article-edit-link, sidebar-bottom
    """
    # Look for copyright section after h1
    for elem in first_h1.find_all_next():
        classes = elem.get("class", []) if hasattr(elem, "get") else []

        # Check for copyright section
        if "section15" in classes:
            return True, elem

        text = elem.get_text() if hasattr(elem, "get_text") else str(elem)
        if text and re.search(r"Section\s*15.*Copyright", text, re.IGNORECASE):
            return True, elem

    # Fallback: look for sidebar or article end
    for elem in first_h1.find_all_next():
        classes = elem.get("class", []) if hasattr(elem, "get") else []

        if "right-sidebar" in classes:
            return True, elem
        if "article-edit-link" in classes:
            return True, elem
        if "sidebar-bottom" in classes:
            return True, elem

    return False, None


def fix_encoding(text: str) -> str:
    """
    Fix UTF-8 content that was incorrectly decoded as latin-1.

    The scraper used response.text which auto-detects encoding.
    Some pages were served without proper Content-Type charset,
    causing UTF-8 bytes to be decoded as latin-1.

    Example: en-dash (–) UTF-8 bytes 0xE2 0x80 0x93 became 'â€"'
    """
    try:
        # Encode back to latin-1 bytes, then decode as UTF-8
        return text.encode('latin-1').decode('utf-8')
    except (UnicodeDecodeError, UnicodeEncodeError):
        # Already valid or unfixable - return as-is
        return text


def extract_clean_markdown(html: str) -> str:
    """
    Extract content from first h1 to end marker, convert to markdown.
    Returns clean markdown string.
    """
    # Fix encoding issues from scraping
    html = fix_encoding(html)

    soup = BeautifulSoup(html, "html.parser")

    # Remove script and style elements
    for element in soup(["script", "style"]):
        element.decompose()

    # Find the article-content div (main content container)
    content_div = soup.find("div", class_="article-content")
    if not content_div:
        # Fallback to article or body
        content_div = soup.find("article") or soup.find("body")
        if not content_div:
            return ""

    # Find first h1 within content
    h1 = content_div.find("h1")
    if not h1:
        return ""

    # Remove everything before the h1 (nav, breadcrumbs, etc.)
    for sibling in list(h1.find_previous_siblings()):
        sibling.decompose()

    # Find and remove the end marker and everything after it
    # Look for copyright section
    section15 = content_div.find("div", class_="section15")
    if section15:
        # Remove section15 and all following siblings
        for sibling in list(section15.find_next_siblings()):
            sibling.decompose()
        section15.decompose()
    else:
        # Fallback: look for Section 15 text
        for elem in content_div.find_all(string=re.compile(r"Section\s*15.*Copyright", re.IGNORECASE)):
            # Find the parent container and remove from there
            parent = elem.find_parent()
            if parent:
                for sibling in list(parent.find_next_siblings()):
                    sibling.decompose()
                parent.decompose()
                break

    # Also remove sidebar elements that might be inside content
    for class_name in ["right-sidebar", "article-edit-link", "sidebar-bottom", "adbox", "widget"]:
        for elem in content_div.find_all(class_=class_name):
            elem.decompose()

    # Convert the cleaned content div to markdown using custom converter
    # that preserves anchor IDs in headings
    converter = AnchorPreservingConverter(heading_style="ATX", strip=["script", "style"])
    markdown_content = converter.convert(str(content_div))

    # Clean up excessive whitespace
    markdown_content = re.sub(r"\n{3,}", "\n\n", markdown_content)
    markdown_content = markdown_content.strip()

    return markdown_content


class MarkdownCache:
    """SQLite-backed cache for markdown content."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._lock = Lock()
        self._ensure_markdown_column()

    def _ensure_markdown_column(self):
        """Add markdown column if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            # Check if column exists
            cursor = conn.execute("PRAGMA table_info(html_cache)")
            columns = [row[1] for row in cursor.fetchall()]

            if "markdown" not in columns:
                log("Adding markdown column to html_cache table...")
                conn.execute("ALTER TABLE html_cache ADD COLUMN markdown TEXT")
                conn.commit()

    def get_html(self, url: str) -> str | None:
        """Get cached HTML for a URL."""
        with sqlite3.connect(self.db_path) as conn:
            conn.text_factory = lambda b: b.decode('utf-8', errors='replace')
            row = conn.execute(
                "SELECT html FROM html_cache WHERE url = ? AND html IS NOT NULL",
                (url,)
            ).fetchone()
            return row[0] if row else None

    def get_markdown(self, url: str) -> str | None:
        """Get cached markdown for a URL."""
        with sqlite3.connect(self.db_path) as conn:
            conn.text_factory = lambda b: b.decode('utf-8', errors='replace')
            row = conn.execute(
                "SELECT markdown FROM html_cache WHERE url = ?",
                (url,)
            ).fetchone()
            return row[0] if row else None

    def set_markdown(self, url: str, markdown: str):
        """Store markdown for a URL."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE html_cache SET markdown = ? WHERE url = ?",
                    (markdown, url)
                )
                conn.commit()

    def get_unconverted_urls(self) -> list[tuple[str, str]]:
        """Get URLs that have HTML but no markdown yet."""
        with sqlite3.connect(self.db_path) as conn:
            conn.text_factory = lambda b: b.decode('utf-8', errors='replace')
            rows = conn.execute(
                "SELECT url, html FROM html_cache WHERE html IS NOT NULL AND markdown IS NULL"
            ).fetchall()
            return rows

    def get_all_urls_with_html(self) -> list[tuple[str, str]]:
        """Get all URLs with HTML content."""
        with sqlite3.connect(self.db_path) as conn:
            conn.text_factory = lambda b: b.decode('utf-8', errors='replace')
            rows = conn.execute(
                "SELECT url, html FROM html_cache WHERE html IS NOT NULL"
            ).fetchall()
            return rows

    def stats(self) -> dict:
        """Get conversion statistics."""
        with sqlite3.connect(self.db_path) as conn:
            total_html = conn.execute(
                "SELECT COUNT(*) FROM html_cache WHERE html IS NOT NULL"
            ).fetchone()[0]

            with_markdown = conn.execute(
                "SELECT COUNT(*) FROM html_cache WHERE markdown IS NOT NULL"
            ).fetchone()[0]

            return {
                "total_html": total_html,
                "with_markdown": with_markdown,
                "pending": total_html - with_markdown
            }


def convert_url(url: str, html: str, cache: MarkdownCache) -> tuple[str, bool, int]:
    """Convert a single URL. Returns (url, success, content_length)."""
    try:
        markdown = extract_clean_markdown(html)
        cache.set_markdown(url, markdown)
        return (url, True, len(markdown))
    except Exception as e:
        return (url, False, 0)


def convert_all(cache: MarkdownCache, force: bool = False, workers: int = 4):
    """Convert all cached HTML to markdown."""
    if force:
        pages = cache.get_all_urls_with_html()
        log(f"Force mode: re-converting all {len(pages)} pages")
    else:
        pages = cache.get_unconverted_urls()
        stats = cache.stats()
        log(f"Total HTML pages: {stats['total_html']}")
        log(f"Already converted: {stats['with_markdown']}")
        log(f"To convert: {len(pages)}")

    if not pages:
        log("Nothing to convert!")
        return

    log(f"\nConverting with {workers} workers...")

    completed = 0
    errors = 0
    total_chars = 0
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(convert_url, url, html, cache): url
            for url, html in pages
        }

        for future in as_completed(futures):
            url, success, length = future.result()
            completed += 1
            if success:
                total_chars += length
            else:
                errors += 1

            # Progress logging every 500 pages
            if completed % 500 == 0:
                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 0
                remaining = len(pages) - completed
                eta = remaining / rate if rate > 0 else 0
                log(f"  [{completed:,}/{len(pages):,}] {rate:.1f}/sec, ETA: {eta:.0f}s")

    elapsed = time.time() - start_time
    log(f"\nDone! Converted {completed:,} pages in {elapsed:.1f}s")
    log(f"  Errors: {errors}")
    log(f"  Total markdown: {total_chars:,} chars ({total_chars/1024/1024:.1f} MB)")


def main():
    parser = argparse.ArgumentParser(description="Convert cached HTML to markdown")
    parser.add_argument("--get", metavar="URL",
                        help="Get markdown for a specific URL")
    parser.add_argument("--preview", metavar="URL",
                        help="Preview markdown extraction without saving")
    parser.add_argument("--stats", action="store_true",
                        help="Show conversion statistics")
    parser.add_argument("--force", action="store_true",
                        help="Re-convert all pages, even if already converted")
    parser.add_argument("--workers", type=int, default=4,
                        help="Number of parallel workers (default: 4)")
    args = parser.parse_args()

    cache = MarkdownCache()

    if args.stats:
        stats = cache.stats()
        log(f"Conversion statistics:")
        log(f"  Total HTML pages: {stats['total_html']:,}")
        log(f"  With markdown: {stats['with_markdown']:,}")
        log(f"  Pending: {stats['pending']:,}")
        return

    if args.get:
        markdown = cache.get_markdown(args.get)
        if markdown:
            print(markdown)
        else:
            log(f"No markdown found for: {args.get}")
            log("Try --preview to generate it from HTML")
        return

    if args.preview:
        html = cache.get_html(args.preview)
        if html:
            markdown = extract_clean_markdown(html)
            log(f"=== Preview for {args.preview} ===")
            log(f"Length: {len(markdown):,} chars")
            log(f"{'='*60}\n")
            print(markdown)
        else:
            log(f"No HTML found for: {args.preview}")
        return

    # Default: convert all
    convert_all(cache, force=args.force, workers=args.workers)


if __name__ == "__main__":
    main()
