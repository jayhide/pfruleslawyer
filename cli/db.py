#!/usr/bin/env python3
"""CLI for querying the html_cache.db database."""

import argparse
import sys
from pathlib import Path

from pfruleslawyer.core import HtmlCacheDB
from pfruleslawyer.core.db import search_urls

# Default path - relative to project root
DEFAULT_DB_PATH = Path(__file__).parent.parent / "scraper" / "html_cache.db"


def main():
    """CLI entry point."""
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
        "--db", type=Path, default=DEFAULT_DB_PATH,
        help=f"Path to database (default: {DEFAULT_DB_PATH})"
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
            print(f"No markdown found for: {args.url}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "html":
        html = db.get_html(args.url)
        if html:
            print(html)
        else:
            print(f"No HTML found for: {args.url}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "has":
        exists = db.has_url(args.url)
        print("yes" if exists else "no")
        sys.exit(0 if exists else 1)

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
            print(f"No URLs matching: {args.pattern}", file=sys.stderr)


if __name__ == "__main__":
    main()
