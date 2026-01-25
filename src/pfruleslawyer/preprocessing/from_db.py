"""Preprocess markdown from database using configuration file."""

import fnmatch
import json
import re
from pathlib import Path

import anthropic
import yaml

from pfruleslawyer.core import HtmlCacheDB
from .processor import (
    process_markdown_full,
    process_markdown_simple,
    process_markdown_template,
    process_markdown_faq,
    process_markdown_class,
)

# Default paths relative to project root
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "config" / "preprocess_config.yaml"
DEFAULT_MANIFESTS_DIR = Path(__file__).parent.parent.parent.parent / "data" / "manifests"


def load_config(config_path: Path | None = None) -> dict:
    """Load configuration from YAML file.

    Args:
        config_path: Path to config file, defaults to config/preprocess_config.yaml

    Returns:
        Configuration dictionary
    """
    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        return yaml.safe_load(f)


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

    e.g., https://paizo.com/paizo/faq/v5748nruor1gw
    -> paizo_faq_v5748nruor1gw.json
    """
    # Remove protocol and domain - handle multiple domains
    path = url
    for domain in ["https://www.d20pfsrd.com/", "https://paizo.com/"]:
        if path.startswith(domain):
            path = path.replace(domain, "")
            break
    path = path.strip("/")
    # Replace slashes with underscores
    filename = path.replace("/", "_")
    # Ensure valid filename
    filename = re.sub(r'[^\w\-]', '_', filename)
    return f"{filename}.json"


def is_index_page(url: str, pattern: str) -> bool:
    """Check if URL is an index page (single-char segment or exact pattern base).

    Index pages are:
    - URLs ending with single-character path segments (e.g., /a/, /b/)
    - The base URL of the pattern (without wildcard)
    """
    # Get the base path from pattern (everything before the first *)
    base = pattern.split("*")[0].rstrip("/")

    # Exact base URL is an index page
    url_normalized = url.rstrip("/")
    if url_normalized == base:
        return True

    # Check for single-char segment at the end
    # e.g., https://www.d20pfsrd.com/magic/all-spells/a/
    path = url_normalized.replace(base, "").strip("/")
    if path and len(path) == 1:
        return True

    return False


def matches_relative_exclude(url: str, exclude_pattern: str) -> bool:
    """Check if URL matches a relative exclude pattern.

    Relative patterns start with '*/' and match against URL suffixes.
    e.g., '*/paizo-*-archetypes/' matches any URL ending with that pattern.
    """
    if not exclude_pattern.startswith("*/"):
        return False

    # Convert relative pattern to glob for suffix matching
    suffix_pattern = exclude_pattern[2:]  # Remove leading */

    # Check if any part of the URL path matches
    return fnmatch.fnmatch(url, f"*/{suffix_pattern}") or fnmatch.fnmatch(url, f"*/{suffix_pattern}/")


def resolve_urls_for_entry(entry: dict, all_urls: list[str]) -> list[tuple[str, str | None, str | None]]:
    """Resolve which URLs match a config entry.

    Supports:
    - url: Single exact URL match
    - urls: List of exact URL matches
    - pattern: Glob pattern with * wildcard
    - exclude: List of URLs or patterns to exclude
    - exclude_index_pages: Auto-exclude single-char index pages

    Exclude patterns can be:
    - Full URLs: "https://www.d20pfsrd.com/feats/combat-feats/"
    - Relative patterns: "*/paizo-*-archetypes/" (matches any URL ending with pattern)

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
        exclude_list = entry.get("exclude", [])
        exclude_index = entry.get("exclude_index_pages", False)

        # Separate full URL excludes from relative pattern excludes
        full_url_excludes = set()
        relative_excludes = []
        for exc in exclude_list:
            if exc.startswith("*/"):
                relative_excludes.append(exc)
            else:
                full_url_excludes.add(exc)

        for url in all_urls:
            if not url_matches_pattern(url, pattern):
                continue

            # Check full URL excludes
            if url in full_url_excludes:
                continue

            # Check index page exclusion
            if exclude_index and is_index_page(url, pattern):
                continue

            # Check relative excludes
            excluded = False
            for rel_exc in relative_excludes:
                if matches_relative_exclude(url, rel_exc):
                    excluded = True
                    break

            if not excluded:
                matched.append((url, name, name_prefix))

    return matched


def extract_title_from_markdown(content: str) -> str:
    """Extract the H1 title from markdown content."""
    match = re.search(r'^# (.+)$', content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return "Unknown"


def process_url(
    client: anthropic.Anthropic | None,
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
        client: Anthropic client instance (can be None for template/faq modes)
        db: Database instance for fetching markdown
        url: URL to process
        mode: Processing mode ("full", "simple", "template", "faq", "class")
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
    import sys

    manifest_filename = url_to_manifest_filename(url)
    output_path = output_dir / manifest_filename

    if verbose:
        print(f"Processing ({mode}): {url}")

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
        elif mode == "faq":
            # No LLM call - pure Python parsing for FAQ Q&A pairs
            manifest = process_markdown_faq(markdown, url, source_name or "Paizo FAQ")
        elif mode == "class":
            # Class documents: split by feature, prepend TOC
            manifest = process_markdown_class(client, markdown, url, source_name, model, timeout)
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


def get_urls_to_process(
    config: dict,
    db: HtmlCacheDB,
    category_filter: str | None = None,
    no_llm: bool = False
) -> dict[str, tuple[str, str, str | None, str | None]]:
    """Get mapping of URLs to their processing parameters.

    Args:
        config: Configuration dictionary
        db: Database instance
        category_filter: Only include entries matching this category
        no_llm: Only include entries that don't require LLM calls

    Returns:
        Dict mapping url -> (mode, category, source_name, name_prefix)
    """
    entries = config.get("entries", [])

    # Filter by category if specified
    if category_filter:
        entries = [e for e in entries if e.get("category") == category_filter]

    # Filter to non-LLM modes if requested
    NO_LLM_MODES = {"template", "faq"}
    if no_llm:
        entries = [e for e in entries if e.get("mode") in NO_LLM_MODES]

    # Get all URLs from database
    all_urls = db.get_all_urls_with_markdown()

    # Resolve URLs for each entry
    url_mode_map: dict[str, tuple[str, str, str | None, str | None]] = {}

    for entry in entries:
        mode = entry.get("mode", "simple")
        category = entry.get("category", "Uncategorized")
        matched = resolve_urls_for_entry(entry, all_urls)

        for url, source_name, name_prefix in matched:
            # Later entries can override earlier ones
            url_mode_map[url] = (mode, category, source_name, name_prefix)

    return url_mode_map
