#!/usr/bin/env python3
"""
Filter d20pfsrd URLs to remove third-party and unwanted content.

Usage:
    poetry run python filter_urls.py
    poetry run python filter_urls.py -i sitemap_urls.txt -o filtered_urls.txt
    poetry run python filter_urls.py --stats  # Show what would be filtered
"""

import argparse
from pathlib import Path

# URL patterns to exclude (case-insensitive matching)
EXCLUDE_PATTERNS = [
    "/3rd-party",
    "3pp-",
    "/extras/",
    "/work-area/",
    "/alternative-rule-systems/",
    "/subscribe/",
    "/gaming-accessories/",
    "/d20pfsrd-com-publishing-products/",
    "/other-rules/",
    "/traps-3rd-party/",
]

# Paths where we want the index page but not individual entries
# Format: (base_path, keep_base_page)
INDEX_ONLY_PATHS = [
    "/gamemastering/traps-hazards-and-special-terrains/traps/",
    "/gamemastering/haunts/",
    "/gamemastering/afflictions/drugs/",
]


def is_third_party_archetype(url: str) -> bool:
    """
    Check if URL is a third-party archetype.

    First-party archetypes have 'paizo' in the archetype folder:
      /classes/.../archetypes/paizo-bard-archetypes/...

    Third-party archetypes have publisher names:
      /classes/.../archetypes/orphaned-bookworm-productions-fighter-archetypes/...
      /classes/.../archetypes/monk-archetypes-varyags-forge/...
    """
    url_lower = url.lower()
    if "/archetypes/" not in url_lower:
        return False

    # Extract the part after /archetypes/
    idx = url_lower.find("/archetypes/")
    after_archetypes = url_lower[idx + len("/archetypes/"):]

    # If there's nothing after /archetypes/, it's just the index page - keep it
    if not after_archetypes or after_archetypes == "/":
        return False

    # Get the first path segment after /archetypes/
    archetype_folder = after_archetypes.split("/")[0]

    # First-party archetypes have 'paizo' in the folder name
    if "paizo" in archetype_folder:
        return False

    # Otherwise it's third-party
    return True


def is_index_only_child(url: str) -> bool:
    """
    Check if URL is a child page of an index-only path.

    We want to keep /gamemastering/haunts/ but exclude
    /gamemastering/haunts/cr-1-3/some-haunt/
    """
    # Extract path from URL
    path = url.replace("https://www.d20pfsrd.com", "").lower()

    for index_path in INDEX_ONLY_PATHS:
        index_path_lower = index_path.lower()
        if path.startswith(index_path_lower):
            # Check if there's more path after the index path
            remainder = path[len(index_path_lower):]
            # If there's additional path content, it's a child page
            if remainder and remainder != "/":
                return True
    return False


def should_exclude(url: str) -> bool:
    """Check if URL matches any exclusion pattern."""
    url_lower = url.lower()
    for pattern in EXCLUDE_PATTERNS:
        if pattern.lower() in url_lower:
            return True

    # Check for third-party archetypes
    if is_third_party_archetype(url):
        return True

    # Check for child pages of index-only paths
    if is_index_only_child(url):
        return True

    return False


def filter_urls(urls: list[str]) -> tuple[list[str], list[str]]:
    """Filter URLs, returning (kept, excluded) tuples."""
    kept = []
    excluded = []
    for url in urls:
        if should_exclude(url):
            excluded.append(url)
        else:
            kept.append(url)
    return kept, excluded


def get_pattern_stats(excluded: list[str]) -> dict[str, int]:
    """Count how many URLs each pattern excluded."""
    stats = {p: 0 for p in EXCLUDE_PATTERNS}
    stats["3rd-party archetypes"] = 0
    stats["index-only children"] = 0
    for url in excluded:
        url_lower = url.lower()
        matched = False
        for pattern in EXCLUDE_PATTERNS:
            if pattern.lower() in url_lower:
                stats[pattern] += 1
                matched = True
                break  # Count each URL only once
        if not matched and is_third_party_archetype(url):
            stats["3rd-party archetypes"] += 1
            matched = True
        if not matched and is_index_only_child(url):
            stats["index-only children"] += 1
    return stats


def get_category_breakdown(urls: list[str]) -> dict[str, int]:
    """Get count by top-level category."""
    categories = {}
    for url in urls:
        path = url.replace("https://www.d20pfsrd.com/", "")
        segment = path.split("/")[0] if path else "(root)"
        categories[segment] = categories.get(segment, 0) + 1
    return categories


def main():
    parser = argparse.ArgumentParser(description="Filter d20pfsrd URLs")
    parser.add_argument("-i", "--input", default="sitemap_urls.txt",
                        help="Input file (default: sitemap_urls.txt)")
    parser.add_argument("-o", "--output", default="filtered_urls.txt",
                        help="Output file (default: filtered_urls.txt)")
    parser.add_argument("--stats", action="store_true",
                        help="Show filtering statistics without writing output")
    args = parser.parse_args()

    # Load URLs
    input_path = Path(args.input)
    urls = input_path.read_text().strip().split("\n")
    print(f"Loaded {len(urls)} URLs from {input_path}")

    # Filter
    kept, excluded = filter_urls(urls)

    print(f"\nFiltering results:")
    print(f"  Kept: {len(kept)}")
    print(f"  Excluded: {len(excluded)}")

    # Show exclusion stats
    print(f"\nExclusions by pattern:")
    pattern_stats = get_pattern_stats(excluded)
    for pattern, count in sorted(pattern_stats.items(), key=lambda x: -x[1]):
        if count > 0:
            print(f"  {pattern}: {count}")

    # Show category breakdown of kept URLs
    print(f"\nKept URLs by category:")
    categories = get_category_breakdown(kept)
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")

    if not args.stats:
        output_path = Path(args.output)
        output_path.write_text("\n".join(kept) + "\n")
        print(f"\nSaved {len(kept)} URLs to {output_path}")


if __name__ == "__main__":
    main()
