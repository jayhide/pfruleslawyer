#!/usr/bin/env python3
"""Analyze URL path hierarchies and count entries at each level."""

import argparse
import sqlite3
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse


def get_urls_from_db(db_path: str) -> list[str]:
    """Get all URLs from the HTML cache database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("SELECT url FROM html_cache")
    urls = [row[0] for row in cursor.fetchall()]
    conn.close()
    return urls


def get_urls_from_file(file_path: str) -> list[str]:
    """Get URLs from a text file (one per line)."""
    with open(file_path) as f:
        return [line.strip() for line in f if line.strip()]


def build_path_tree(urls: list[str]) -> dict[str, int]:
    """Build a tree of path counts from URLs.

    Returns a dict mapping path prefixes to counts of URLs under that path.
    """
    counts = defaultdict(int)

    for url in urls:
        parsed = urlparse(url)
        path = parsed.path.strip("/")

        if not path:
            counts["/"] += 1
            continue

        parts = path.split("/")

        # Count this URL at each level of its path hierarchy
        for i in range(1, len(parts) + 1):
            prefix = "/" + "/".join(parts[:i]) + "/"
            counts[prefix] += 1

    return dict(counts)


def print_tree(counts: dict[str, int], min_count: int = 1, max_depth: int | None = None):
    """Print the path tree in a hierarchical format."""
    # Sort by path for consistent output
    sorted_paths = sorted(counts.keys())

    for path in sorted_paths:
        count = counts[path]

        if count < min_count:
            continue

        depth = path.strip("/").count("/") + 1 if path != "/" else 0

        if max_depth is not None and depth > max_depth:
            continue

        indent = "  " * depth
        print(f"{indent}{path} ({count})")


def print_flat(counts: dict[str, int], min_count: int = 1, sort_by: str = "path"):
    """Print counts in a flat format."""
    items = [(path, count) for path, count in counts.items() if count >= min_count]

    if sort_by == "count":
        items.sort(key=lambda x: (-x[1], x[0]))
    else:
        items.sort(key=lambda x: x[0])

    # Find max path length for alignment
    max_len = max(len(path) for path, _ in items) if items else 0

    for path, count in items:
        print(f"{path:<{max_len}}  {count:>6}")


def main():
    parser = argparse.ArgumentParser(description="Analyze URL path hierarchies")
    parser.add_argument(
        "-i", "--input",
        help="Input file (URLs text file). If not specified, reads from html_cache.db"
    )
    parser.add_argument(
        "--db",
        default="scraper/html_cache.db",
        help="Path to HTML cache database (default: scraper/html_cache.db)"
    )
    parser.add_argument(
        "--min-count", "-m",
        type=int,
        default=1,
        help="Only show paths with at least this many URLs (default: 1)"
    )
    parser.add_argument(
        "--max-depth", "-d",
        type=int,
        help="Maximum depth to display (default: no limit)"
    )
    parser.add_argument(
        "--flat", "-f",
        action="store_true",
        help="Output in flat format instead of tree"
    )
    parser.add_argument(
        "--sort-by-count", "-c",
        action="store_true",
        help="Sort by count descending (only with --flat)"
    )
    parser.add_argument(
        "--path", "-p",
        help="Only analyze URLs under this path (e.g., /skills/ or https://www.d20pfsrd.com/skills/)"
    )

    args = parser.parse_args()

    # Get URLs from input source
    if args.input:
        urls = get_urls_from_file(args.input)
        print(f"Loaded {len(urls)} URLs from {args.input}")
    else:
        db_path = args.db
        if not Path(db_path).exists():
            # Try relative to script location
            script_dir = Path(__file__).parent
            db_path = script_dir / "html_cache.db"
        urls = get_urls_from_db(str(db_path))
        print(f"Loaded {len(urls)} URLs from database")

    # Filter by path prefix if specified
    if args.path:
        # Normalize the path filter
        path_filter = args.path
        # Remove domain if full URL provided
        if path_filter.startswith("http"):
            path_filter = urlparse(path_filter).path
        # Ensure leading slash
        if not path_filter.startswith("/"):
            path_filter = "/" + path_filter
        # Ensure trailing slash for prefix matching
        if not path_filter.endswith("/"):
            path_filter = path_filter + "/"

        original_count = len(urls)
        urls = [u for u in urls if urlparse(u).path.startswith(path_filter.rstrip("/"))]
        print(f"Filtered to {len(urls)} URLs under {path_filter}")

    print()

    # Build and display the tree
    counts = build_path_tree(urls)

    if args.flat:
        sort_by = "count" if args.sort_by_count else "path"
        print_flat(counts, min_count=args.min_count, sort_by=sort_by)
    else:
        print_tree(counts, min_count=args.min_count, max_depth=args.max_depth)


if __name__ == "__main__":
    main()
