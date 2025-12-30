#!/usr/bin/env python3
"""Remove markdown links from files, preserving the link text.

Example: [bards](https://www.d20pfsrd.com/classes/core-classes/bard) -> bards
"""

import argparse
import re
from pathlib import Path


def remove_links(content: str) -> str:
    """Remove markdown links, keeping only the link text."""
    # Pattern matches [text](url) and replaces with just text
    pattern = r'\[([^\]]+)\]\([^)]+\)'
    return re.sub(pattern, r'\1', content)


def process_file(filepath: Path, dry_run: bool = False) -> int:
    """Process a single file. Returns count of links removed."""
    content = filepath.read_text()

    # Count links before removal
    pattern = r'\[([^\]]+)\]\([^)]+\)'
    links = re.findall(pattern, content)
    count = len(links)

    if count == 0:
        return 0

    new_content = remove_links(content)

    if dry_run:
        print(f"{filepath}: would remove {count} links")
    else:
        filepath.write_text(new_content)
        print(f"{filepath}: removed {count} links")

    return count


def main():
    parser = argparse.ArgumentParser(description="Remove markdown links from files")
    parser.add_argument("files", nargs="*", help="Files to process (default: all .md in rules/)")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Show what would be done without making changes")
    args = parser.parse_args()

    if args.files:
        files = [Path(f) for f in args.files]
    else:
        rules_dir = Path(__file__).parent / "rules"
        files = list(rules_dir.glob("*.md"))

    total = 0
    for f in files:
        if f.exists():
            total += process_file(f, args.dry_run)
        else:
            print(f"Warning: {f} not found")

    action = "Would remove" if args.dry_run else "Removed"
    print(f"\n{action} {total} links total from {len(files)} files")


if __name__ == "__main__":
    main()
