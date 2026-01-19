#!/usr/bin/env python3
"""CLI for preprocessing markdown from database using configuration."""

import argparse
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from pfruleslawyer.core import HtmlCacheDB
from pfruleslawyer.preprocessing import (
    load_config,
    url_to_manifest_filename,
    get_urls_to_process,
    process_url,
)

load_dotenv()

# Default paths - relative to project root
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "preprocess_config.json"
DEFAULT_MANIFESTS_DIR = Path(__file__).parent.parent / "data" / "manifests"
DEFAULT_DB_PATH = Path(__file__).parent.parent / "scraper" / "html_cache.db"


def main():
    parser = argparse.ArgumentParser(
        description="Preprocess markdown from database using configuration"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to config file (default: {DEFAULT_CONFIG_PATH})"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to database (default: {DEFAULT_DB_PATH})"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_MANIFESTS_DIR,
        help=f"Output directory for manifests (default: {DEFAULT_MANIFESTS_DIR})"
    )
    parser.add_argument(
        "--category",
        type=str,
        help="Only process entries matching this category"
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-20250514",
        help="Claude model to use (default: claude-sonnet-4-20250514)"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="API timeout in seconds (default: 300)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print detailed progress"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without making API calls"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess URLs even if manifest already exists"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show statistics about what would be processed and exit"
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Only process entries that don't require LLM calls (template and faq modes)"
    )

    args = parser.parse_args()

    # Load config
    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    entries = config.get("entries", [])

    if not entries:
        print("No entries in config file")
        return

    # Initialize database
    db = HtmlCacheDB(args.db)

    # Get URLs to process
    url_mode_map = get_urls_to_process(
        config, db,
        category_filter=args.category,
        no_llm=args.no_llm
    )

    if not url_mode_map:
        if args.category:
            print(f"No URLs matched for category: {args.category}")
        elif args.no_llm:
            print("No URLs matched for non-LLM modes (template, faq)")
        else:
            print("No URLs matched any config entries")
        return

    # Show stats if requested
    if args.stats:
        print(f"\nMatched {len(url_mode_map)} URLs:")
        by_category: dict[str, list[str]] = {}
        for url, (mode, category, _, _) in url_mode_map.items():
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(url)

        for category, urls in sorted(by_category.items()):
            print(f"  {category}: {len(urls)} URLs")
        return

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Filter out URLs with existing manifests (unless --force)
    urls_to_process = []
    skipped = 0
    for url in url_mode_map:
        manifest_path = args.output_dir / url_to_manifest_filename(url)
        if manifest_path.exists() and not args.force:
            skipped += 1
        else:
            urls_to_process.append(url)

    if skipped > 0:
        print(f"Skipping {skipped} URLs with existing manifests (use --force to reprocess)")

    if not urls_to_process:
        print("No URLs to process")
        return

    # Check for API key (unless dry run or no-llm mode)
    if not args.dry_run and not args.no_llm and not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    # Initialize client (not needed for dry run or no-llm mode)
    client = None
    if not args.dry_run and not args.no_llm:
        client = anthropic.Anthropic()

    print(f"\nProcessing {len(urls_to_process)} URLs...")

    success_count = 0
    for i, url in enumerate(urls_to_process, 1):
        mode, category, source_name, name_prefix = url_mode_map[url]

        if args.verbose:
            print(f"\n[{i}/{len(urls_to_process)}] ({category})")

        success = process_url(
            client=client,
            db=db,
            url=url,
            mode=mode,
            output_dir=args.output_dir,
            source_name=source_name,
            name_prefix=name_prefix,
            category=category,
            model=args.model,
            timeout=args.timeout,
            verbose=args.verbose,
            dry_run=args.dry_run
        )

        if success:
            success_count += 1

    print(f"\nCompleted: {success_count}/{len(urls_to_process)} URLs processed successfully")

    if success_count < len(urls_to_process):
        sys.exit(1)


if __name__ == "__main__":
    main()
