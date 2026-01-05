#!/usr/bin/env python3
"""
Fetch all URLs from d20pfsrd.com sitemap and by crawling category pages.

Usage:
    poetry run python fetch_sitemap_urls.py
    poetry run python fetch_sitemap_urls.py -o urls.txt
    poetry run python fetch_sitemap_urls.py --pages-only  # Skip taxonomy sitemaps
    poetry run python fetch_sitemap_urls.py --crawl       # Also crawl category pages
"""

import argparse
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

SITEMAP_INDEX_URL = "https://www.d20pfsrd.com/wp-sitemap.xml"
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
BASE_URL = "https://www.d20pfsrd.com"

# Use a browser user agent - the site blocks default requests user agents
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Main content sections to crawl
SEED_URLS = [
    "/classes/",
    "/races/",
    "/feats/",
    "/skills/",
    "/traits/",
    "/equipment/",
    "/magic-items/",
    "/magic/",
    "/gamemastering/",
    "/bestiary/",
    "/basics-ability-scores/",
    "/alignment-description/",
]


def fetch_xml(url: str) -> ET.Element | None:
    """Fetch and parse XML from a URL. Returns None if fetch fails."""
    print(f"Fetching: {url}")
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        # Note: Server sometimes returns 404 but still serves valid XML content
        # So we try to parse regardless of status code
        return ET.fromstring(response.content)
    except ET.ParseError:
        print(f"  -> Not valid XML (status {response.status_code})")
        return None
    except requests.exceptions.RequestException as e:
        print(f"  -> Request error: {e}")
        return None


def get_nested_sitemaps(sitemap_index_url: str) -> list[str]:
    """Get all nested sitemap URLs from the sitemap index."""
    root = fetch_xml(sitemap_index_url)
    if root is None:
        return []
    sitemaps = []
    for sitemap in root.findall("sm:sitemap", SITEMAP_NS):
        loc = sitemap.find("sm:loc", SITEMAP_NS)
        if loc is not None and loc.text:
            sitemaps.append(loc.text)
    return sitemaps


def get_urls_from_sitemap(sitemap_url: str) -> list[str]:
    """Extract all URLs from a sitemap."""
    root = fetch_xml(sitemap_url)
    if root is None:
        return []
    urls = []
    for url_elem in root.findall("sm:url", SITEMAP_NS):
        loc = url_elem.find("sm:loc", SITEMAP_NS)
        if loc is not None and loc.text:
            urls.append(loc.text)
    return urls


def fetch_all_urls(pages_only: bool = False) -> list[str]:
    """Fetch all URLs from the sitemap index and all nested sitemaps."""
    nested_sitemaps = get_nested_sitemaps(SITEMAP_INDEX_URL)

    if pages_only:
        # Filter to only page sitemaps (skip posts and taxonomies)
        nested_sitemaps = [s for s in nested_sitemaps if "posts-page" in s]

    print(f"Found {len(nested_sitemaps)} nested sitemaps")

    all_urls = []
    for sitemap_url in nested_sitemaps:
        urls = get_urls_from_sitemap(sitemap_url)
        print(f"  -> {len(urls)} URLs")
        all_urls.extend(urls)

    return all_urls


def extract_links_from_page(url: str, html: str) -> list[str]:
    """Extract all internal links from an HTML page."""
    soup = BeautifulSoup(html, "html.parser")
    links = []

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        # Convert relative URLs to absolute
        full_url = urljoin(url, href)

        # Only keep d20pfsrd.com URLs
        parsed = urlparse(full_url)
        if parsed.netloc in ("www.d20pfsrd.com", "d20pfsrd.com"):
            # Normalize: remove fragments, ensure trailing slash consistency
            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            # Remove trailing slash for consistency (except root)
            if clean_url.endswith("/") and len(parsed.path) > 1:
                clean_url = clean_url.rstrip("/")
            links.append(clean_url)

    return links


def crawl_section(start_url: str, max_pages: int = 5000, delay: float = 0.5) -> set[str]:
    """
    Crawl a section of the site starting from a seed URL.
    Only follows links that are under the same path prefix.
    """
    parsed_start = urlparse(start_url)
    path_prefix = parsed_start.path.rstrip("/")

    visited = set()
    to_visit = {start_url}
    discovered = set()

    print(f"\nCrawling section: {path_prefix}")

    while to_visit and len(visited) < max_pages:
        url = to_visit.pop()
        if url in visited:
            continue

        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            visited.add(url)
            discovered.add(url)

            # Extract links
            links = extract_links_from_page(url, response.text)

            for link in links:
                parsed_link = urlparse(link)
                # Only follow links under the same section
                if parsed_link.path.startswith(path_prefix) and link not in visited:
                    to_visit.add(link)
                # But discover all d20pfsrd links
                discovered.add(link)

            if len(visited) % 100 == 0:
                print(f"  Crawled {len(visited)} pages, discovered {len(discovered)} URLs")

            time.sleep(delay)

        except Exception as e:
            print(f"  Error crawling {url}: {e}")
            visited.add(url)  # Don't retry

    print(f"  Section complete: crawled {len(visited)}, discovered {len(discovered)}")
    return discovered


def crawl_all_sections(delay: float = 0.5) -> list[str]:
    """Crawl all main content sections to discover URLs."""
    all_urls = set()

    for seed_path in SEED_URLS:
        seed_url = BASE_URL + seed_path
        urls = crawl_section(seed_url, delay=delay)
        all_urls.update(urls)
        print(f"Total discovered so far: {len(all_urls)}")

    return list(all_urls)


def main():
    parser = argparse.ArgumentParser(description="Fetch all URLs from d20pfsrd.com sitemap")
    parser.add_argument("-o", "--output", type=str, default="sitemap_urls.txt",
                        help="Output file for URLs (default: sitemap_urls.txt)")
    parser.add_argument("--pages-only", action="store_true",
                        help="Only fetch page sitemaps (skip posts and taxonomies)")
    parser.add_argument("--crawl", action="store_true",
                        help="Also crawl main content sections to discover more URLs")
    parser.add_argument("--crawl-only", action="store_true",
                        help="Only crawl (skip sitemap)")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="Delay between requests when crawling (default: 0.5s)")
    args = parser.parse_args()

    urls = []

    # Fetch from sitemap
    if not args.crawl_only:
        print("=== Fetching from sitemap ===")
        sitemap_urls = fetch_all_urls(pages_only=args.pages_only)
        urls.extend(sitemap_urls)

    # Crawl sections
    if args.crawl or args.crawl_only:
        print("\n=== Crawling content sections ===")
        crawled_urls = crawl_all_sections(delay=args.delay)
        urls.extend(crawled_urls)

    # Remove duplicates while preserving order
    seen = set()
    unique_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)

    print(f"\nTotal URLs: {len(urls)}")
    print(f"Unique URLs: {len(unique_urls)}")

    # Save to file
    output_path = Path(args.output)
    output_path.write_text("\n".join(unique_urls) + "\n")
    print(f"Saved to: {output_path}")

    # Print some stats about URL patterns
    print("\nURL pattern breakdown:")
    patterns = {}
    for url in unique_urls:
        # Get first path segment after domain
        path = url.replace("https://www.d20pfsrd.com/", "")
        segment = path.split("/")[0] if path else "(root)"
        patterns[segment] = patterns.get(segment, 0) + 1

    for pattern, count in sorted(patterns.items(), key=lambda x: -x[1])[:20]:
        print(f"  {pattern}: {count}")


if __name__ == "__main__":
    main()
