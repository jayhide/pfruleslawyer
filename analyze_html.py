#!/usr/bin/env python3
"""
Analyze cached HTML to test content extraction heuristics.

Usage:
    poetry run python analyze_html.py              # Analyze all cached pages
    poetry run python analyze_html.py --limit 100  # Analyze first 100 pages
    poetry run python analyze_html.py --show-missing-h1     # Show URLs without h1
    poetry run python analyze_html.py --show-missing-copyright  # Show URLs without copyright
    poetry run python analyze_html.py --show-short 500      # Show URLs with <500 chars
"""

import argparse
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup
from markdownify import markdownify as md

DB_PATH = Path("html_cache.db")


def log(msg: str):
    """Print with immediate flush for real-time logging."""
    print(msg, flush=True)


@dataclass
class PageAnalysis:
    url: str
    h1_count: int
    h1_text: str | None
    has_copyright: bool
    used_fallback: bool  # True if we used sidebar/article fallback instead of copyright
    content_length: int  # markdown chars between h1 and end marker
    error: str | None = None


def find_content_end(soup: BeautifulSoup, first_h1) -> tuple[bool, bool, any]:
    """
    Find where content ends. Returns (has_copyright, used_fallback, end_element).

    Priority:
    1. Copyright section (div.section15 or "Section 15" text)
    2. Fallback: right-sidebar, article-edit-link, or </article>
    """
    # Look for copyright section after h1
    for elem in first_h1.find_all_next():
        classes = elem.get("class", []) if hasattr(elem, "get") else []

        # Check for copyright section
        if "section15" in classes:
            return True, False, elem

        text = elem.get_text() if hasattr(elem, "get_text") else str(elem)
        if text and re.search(r"Section\s*15.*Copyright", text, re.IGNORECASE):
            return True, False, elem

    # Fallback: look for sidebar or article end
    for elem in first_h1.find_all_next():
        classes = elem.get("class", []) if hasattr(elem, "get") else []

        # Stop at right sidebar
        if "right-sidebar" in classes:
            return False, True, elem

        # Stop at article edit link section
        if "article-edit-link" in classes:
            return False, True, elem

        # Stop at sidebar-bottom
        if "sidebar-bottom" in classes:
            return False, True, elem

    # Last resort: end of article
    article = soup.find("article")
    if article:
        return False, True, None  # Use full article

    return False, True, None


def extract_content(html: str) -> tuple[str | None, bool, bool, str]:
    """
    Extract content between first h1 and end marker.
    Returns (h1_text, has_copyright, used_fallback, markdown_content).
    """
    soup = BeautifulSoup(html, "html.parser")

    # Find all h1 tags
    h1_tags = soup.find_all("h1")
    h1_text = h1_tags[0].get_text(strip=True) if h1_tags else None

    if not h1_tags:
        return None, False, False, ""

    first_h1 = h1_tags[0]

    # Find where content ends
    has_copyright, used_fallback, end_element = find_content_end(soup, first_h1)

    # Get content from h1 to end marker
    content_parts = [str(first_h1)]
    for sibling in first_h1.find_all_next():
        # Stop if we've reached the end element
        if end_element is not None and sibling == end_element:
            break

        # Also check by class for safety
        classes = sibling.get("class", []) if hasattr(sibling, "get") else []
        if any(c in classes for c in ["section15", "right-sidebar", "article-edit-link", "sidebar-bottom"]):
            break

        # Check for copyright text
        text = sibling.get_text() if hasattr(sibling, "get_text") else ""
        if text and re.search(r"Section\s*15.*Copyright", text, re.IGNORECASE):
            break

        content_parts.append(str(sibling))

    content_html = "".join(content_parts)

    # Convert to markdown
    markdown_content = md(content_html, heading_style="ATX", strip=["script", "style"])

    # Clean up excessive whitespace
    markdown_content = re.sub(r"\n{3,}", "\n\n", markdown_content)

    return h1_text, has_copyright, used_fallback, markdown_content


def analyze_page(url: str, html: str) -> PageAnalysis:
    """Analyze a single page."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        h1_tags = soup.find_all("h1")
        h1_count = len(h1_tags)

        # Extract content with fallback logic
        h1_text, has_copyright, used_fallback, markdown_content = extract_content(html)
        content_length = len(markdown_content)

        return PageAnalysis(
            url=url,
            h1_count=h1_count,
            h1_text=h1_text,
            has_copyright=has_copyright,
            used_fallback=used_fallback,
            content_length=content_length,
        )
    except Exception as e:
        return PageAnalysis(
            url=url,
            h1_count=0,
            h1_text=None,
            has_copyright=False,
            used_fallback=False,
            content_length=0,
            error=str(e),
        )


def load_cached_pages(limit: int | None = None) -> list[tuple[str, str]]:
    """Load cached pages from database."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.text_factory = lambda b: b.decode('utf-8', errors='replace')
        query = "SELECT url, html FROM html_cache WHERE html IS NOT NULL"
        if limit:
            query += f" LIMIT {limit}"
        rows = conn.execute(query).fetchall()
        return rows


def main():
    parser = argparse.ArgumentParser(description="Analyze cached HTML pages")
    parser.add_argument("--limit", type=int, help="Limit number of pages to analyze")
    parser.add_argument("--show-missing-h1", action="store_true",
                        help="Show URLs without h1 tags")
    parser.add_argument("--show-missing-copyright", action="store_true",
                        help="Show URLs without copyright section")
    parser.add_argument("--show-short", type=int, metavar="N",
                        help="Show URLs with less than N chars of content")
    parser.add_argument("--show-multi-h1", action="store_true",
                        help="Show URLs with multiple h1 tags")
    parser.add_argument("--show-fallback", action="store_true",
                        help="Show URLs that used fallback end detection")
    args = parser.parse_args()

    log("Loading cached pages...")
    start_time = time.time()
    pages = load_cached_pages(args.limit)
    log(f"Loaded {len(pages)} pages in {time.time() - start_time:.1f}s")
    log(f"Analyzing pages...")
    log("")

    results: list[PageAnalysis] = []
    analysis_start = time.time()

    for i, (url, html) in enumerate(pages):
        result = analyze_page(url, html)
        results.append(result)

        # Progress logging every 500 pages
        if (i + 1) % 500 == 0:
            elapsed = time.time() - analysis_start
            rate = (i + 1) / elapsed
            remaining = len(pages) - (i + 1)
            eta = remaining / rate if rate > 0 else 0
            log(f"  [{i + 1:,}/{len(pages):,}] {rate:.1f} pages/sec, ETA: {eta:.0f}s")

    total_time = time.time() - analysis_start
    log(f"\nAnalysis complete in {total_time:.1f}s ({len(pages)/total_time:.1f} pages/sec)")

    # Calculate statistics
    total = len(results)
    with_h1 = sum(1 for r in results if r.h1_count >= 1)
    with_single_h1 = sum(1 for r in results if r.h1_count == 1)
    with_multi_h1 = sum(1 for r in results if r.h1_count > 1)
    with_no_h1 = sum(1 for r in results if r.h1_count == 0)
    with_copyright = sum(1 for r in results if r.has_copyright)
    with_fallback = sum(1 for r in results if r.used_fallback)
    with_errors = sum(1 for r in results if r.error)

    content_lengths = [r.content_length for r in results if r.content_length > 0]
    avg_length = sum(content_lengths) / len(content_lengths) if content_lengths else 0
    min_length = min(content_lengths) if content_lengths else 0
    max_length = max(content_lengths) if content_lengths else 0

    log(f"\n{'='*60}")
    log("ANALYSIS RESULTS")
    log(f"{'='*60}")
    log(f"Total pages analyzed: {total:,}")
    log(f"  Errors: {with_errors}")
    log("")
    log("H1 Tags:")
    log(f"  With h1: {with_h1:,} ({100*with_h1/total:.1f}%)")
    log(f"  Single h1: {with_single_h1:,} ({100*with_single_h1/total:.1f}%)")
    log(f"  Multiple h1: {with_multi_h1:,} ({100*with_multi_h1/total:.1f}%)")
    log(f"  No h1: {with_no_h1:,} ({100*with_no_h1/total:.1f}%)")
    log("")
    log("Content End Detection:")
    log(f"  Copyright section: {with_copyright:,} ({100*with_copyright/total:.1f}%)")
    log(f"  Fallback (sidebar): {with_fallback:,} ({100*with_fallback/total:.1f}%)")
    log("")
    log("Content Length (markdown chars):")
    log(f"  Average: {avg_length:,.0f}")
    log(f"  Min: {min_length:,}")
    log(f"  Max: {max_length:,}")

    # Distribution buckets
    buckets = [0, 100, 500, 1000, 5000, 10000, 50000, float("inf")]
    log("\n  Distribution:")
    for i in range(len(buckets) - 1):
        low, high = buckets[i], buckets[i + 1]
        count = sum(1 for r in results if low <= r.content_length < high)
        label = f"{low:,}-{high:,}" if high != float("inf") else f"{low:,}+"
        log(f"    {label}: {count:,} ({100*count/total:.1f}%)")

    # Show specific issues if requested
    if args.show_missing_h1:
        missing = [r for r in results if r.h1_count == 0]
        log(f"\n{'='*60}")
        log(f"URLs without h1 ({len(missing)}):")
        for r in missing[:20]:
            log(f"  {r.url}")
        if len(missing) > 20:
            log(f"  ... and {len(missing) - 20} more")

    if args.show_multi_h1:
        multi = [r for r in results if r.h1_count > 1]
        log(f"\n{'='*60}")
        log(f"URLs with multiple h1 tags ({len(multi)}):")
        for r in multi[:20]:
            log(f"  {r.url} ({r.h1_count} h1s, first: {r.h1_text[:50] if r.h1_text else 'N/A'}...)")
        if len(multi) > 20:
            log(f"  ... and {len(multi) - 20} more")

    if args.show_missing_copyright:
        missing = [r for r in results if not r.has_copyright and not r.used_fallback]
        log(f"\n{'='*60}")
        log(f"URLs without copyright or fallback ({len(missing)}):")
        for r in missing[:20]:
            log(f"  {r.url}")
        if len(missing) > 20:
            log(f"  ... and {len(missing) - 20} more")

    if args.show_fallback:
        fallback = [r for r in results if r.used_fallback]
        log(f"\n{'='*60}")
        log(f"URLs using fallback detection ({len(fallback)}):")
        for r in fallback[:20]:
            log(f"  {r.content_length:,} chars: {r.url}")
        if len(fallback) > 20:
            log(f"  ... and {len(fallback) - 20} more")

    if args.show_short:
        short = [r for r in results if 0 < r.content_length < args.show_short]
        short.sort(key=lambda r: r.content_length)
        log(f"\n{'='*60}")
        log(f"URLs with <{args.show_short} chars ({len(short)}):")
        for r in short[:20]:
            log(f"  {r.content_length:,} chars: {r.url}")
        if len(short) > 20:
            log(f"  ... and {len(short) - 20} more")


if __name__ == "__main__":
    main()
