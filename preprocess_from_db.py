#!/usr/bin/env python3
"""Preprocess markdown from database using configuration file."""

import argparse
import fnmatch
import json
import os
import re
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from db import HtmlCacheDB
from preprocess_sections import (
    process_markdown_full,
    process_markdown_simple,
    process_markdown_template,
    get_source_name,
)

load_dotenv()

CONFIG_PATH = Path("preprocess_config.json")
MANIFESTS_DIR = Path("manifests")


def load_config(config_path: Path = CONFIG_PATH) -> dict:
    """Load configuration from JSON file."""
    if not config_path.exists():
        print(f"Error: Config file '{config_path}' not found", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        return json.load(f)


def url_matches_pattern(url: str, pattern: str) -> bool:
    """Check if URL matches a glob pattern.

    Supports * as wildcard for any characters.
    """
    # Convert glob pattern to regex
    regex_pattern = fnmatch.translate(pattern)
    return bool(re.match(regex_pattern, url))


def url_to_manifest_filename(url: str) -> str:
    """Convert URL to a manifest filename.

    e.g., https://www.d20pfsrd.com/feats/combat-feats/power-attack-combat/
    -> feats_combat-feats_power-attack-combat.json
    """
    # Remove protocol and domain
    path = url.replace("https://www.d20pfsrd.com/", "").strip("/")
    # Replace slashes with underscores
    filename = path.replace("/", "_")
    # Ensure valid filename
    filename = re.sub(r'[^\w\-]', '_', filename)
    return f"{filename}.json"


def resolve_urls_for_entry(entry: dict, all_urls: list[str]) -> list[tuple[str, str | None, str | None]]:
    """Resolve which URLs match a config entry.

    Returns:
        List of (url, name, name_prefix) tuples.
    """
    matched = []
    name = entry.get("name")
    name_prefix = entry.get("name_prefix")
    all_urls_set = set(all_urls)

    if "url" in entry:
        # Single exact match
        if entry["url"] in all_urls_set:
            matched.append((entry["url"], name, name_prefix))
    elif "urls" in entry:
        # List of exact matches
        for url in entry["urls"]:
            if url in all_urls_set:
                matched.append((url, name, name_prefix))
    elif "pattern" in entry:
        # Pattern match
        pattern = entry["pattern"]
        excludes = set(entry.get("exclude", []))

        for url in all_urls:
            if url_matches_pattern(url, pattern) and url not in excludes:
                matched.append((url, name, name_prefix))

    return matched


def extract_title_from_markdown(content: str) -> str:
    """Extract the H1 title from markdown content."""
    match = re.search(r'^# (.+)$', content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return "Unknown"


def process_url(
    client: anthropic.Anthropic,
    db: HtmlCacheDB,
    url: str,
    mode: str,
    output_dir: Path,
    source_name: str | None = None,
    name_prefix: str | None = None,
    category: str = "Uncategorized",
    model: str = "claude-sonnet-4-20250514",
    timeout: float = 300.0,
    verbose: bool = False,
    dry_run: bool = False
) -> bool:
    """Process a single URL and save its manifest.

    Args:
        client: Anthropic client instance
        db: Database instance for fetching markdown
        url: URL to process
        mode: Processing mode ("full" or "simple")
        output_dir: Directory to save manifest
        source_name: Human-readable name for this source (from config)
        name_prefix: Prefix to prepend to page title (e.g., "Skill" -> "Skill: Acrobatics")
        category: Category for this source (e.g., "Spells", "Skills", "Core Rules")
        model: Claude model to use
        timeout: API timeout in seconds
        verbose: Print detailed progress
        dry_run: Preview without making API calls

    Returns:
        True if successful, False otherwise
    """
    manifest_filename = url_to_manifest_filename(url)
    output_path = output_dir / manifest_filename

    if verbose:
        mode_str = "full" if mode == "full" else "simple"
        print(f"Processing ({mode_str}): {url}")

    if dry_run:
        print(f"  -> Would save to {output_path}")
        return True

    # Get markdown from database
    markdown = db.get_markdown(url)
    if not markdown:
        print(f"  Error: No markdown found for {url}", file=sys.stderr)
        return False

    try:
        if mode == "full":
            manifest = process_markdown_full(client, markdown, url, model, timeout)
        elif mode == "template":
            # No LLM call - pure template-based processing
            manifest = process_markdown_template(markdown, url, category)
        else:
            manifest = process_markdown_simple(client, markdown, url, model, timeout)

        # Override source_name if provided in config
        if source_name:
            manifest["source_name"] = source_name
        elif name_prefix:
            # Generate name from prefix + page title
            title = extract_title_from_markdown(markdown)
            manifest["source_name"] = f"{name_prefix}: {title}"

        # Store category for search weight customization
        manifest["category"] = category

        # Save manifest
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        if verbose:
            section_count = len(manifest.get("sections", []))
            print(f"  -> Generated {section_count} section(s)")
            print(f"  -> Saved to {output_path}")

        return True

    except anthropic.APITimeoutError:
        print(f"  Timeout processing {url}", file=sys.stderr)
        return False
    except anthropic.APIError as e:
        print(f"  API error: {e}", file=sys.stderr)
        return False
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}", file=sys.stderr)
        return False
    except ValueError as e:
        print(f"  Validation error: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Preprocess markdown from database using configuration"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=CONFIG_PATH,
        help=f"Path to config file (default: {CONFIG_PATH})"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("scraper/html_cache.db"),
        help="Path to database (default: scraper/html_cache.db)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=MANIFESTS_DIR,
        help=f"Output directory for manifests (default: {MANIFESTS_DIR})"
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

    args = parser.parse_args()

    # Load config
    config = load_config(args.config)
    entries = config.get("entries", [])

    if not entries:
        print("No entries in config file")
        return

    # Filter by category if specified
    if args.category:
        entries = [e for e in entries if e.get("category") == args.category]
        if not entries:
            print(f"No entries found for category: {args.category}")
            return

    # Initialize database
    db = HtmlCacheDB(args.db)

    # Get all URLs from database
    print(f"Loading URLs from database...")
    all_urls = db.get_all_urls_with_markdown()
    print(f"Found {len(all_urls)} URLs with markdown")

    # Resolve URLs for each entry
    # url -> (mode, category, source_name, name_prefix)
    url_mode_map: dict[str, tuple[str, str, str | None, str | None]] = {}

    for entry in entries:
        mode = entry.get("mode", "simple")
        category = entry.get("category", "Uncategorized")
        matched = resolve_urls_for_entry(entry, all_urls)

        for url, source_name, name_prefix in matched:
            # Later entries can override earlier ones
            url_mode_map[url] = (mode, category, source_name, name_prefix)

    if not url_mode_map:
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

    # Check for API key (unless dry run)
    if not args.dry_run and not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    # Initialize client
    client = anthropic.Anthropic() if not args.dry_run else None

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
