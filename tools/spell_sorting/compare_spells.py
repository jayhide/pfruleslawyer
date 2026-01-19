#!/usr/bin/env python3
"""
Compare druid and wizard spell lists to find overlapping and unique spells.
"""

import re
from pathlib import Path


def parse_spell_list(filepath: str) -> dict[str, set[str]]:
    """
    Parse a spell list file and return a dict mapping spell level to set of spell names.
    """
    content = Path(filepath).read_text()

    spells_by_level: dict[str, set[str]] = {}
    current_level = None

    # Patterns to match level headers
    level_pattern = re.compile(r'^(\d+)(?:st|nd|rd|th)?-Level|^0-Level', re.IGNORECASE)

    # Patterns to skip (school headers, empty lines, column headers)
    skip_patterns = [
        re.compile(r'^(Abjuration|Conjuration|Divination|Enchantment|Evocation|Illusion|Necromancy|Transmutation|Universal)$', re.IGNORECASE),
        re.compile(r'^\s*$'),
        re.compile(r'Spell Name\s+Comp\.\s+Description', re.IGNORECASE),
    ]

    for line in content.split('\n'):
        # Remove line numbers from the beginning (e.g., "     1→")
        line = re.sub(r'^\s*\d+→', '', line).strip()

        if not line:
            continue

        # Check for level header
        level_match = level_pattern.search(line)
        if level_match:
            # Extract level number
            if '0-Level' in line or '0th' in line.lower():
                current_level = '0'
            else:
                level_num = re.search(r'(\d+)', line)
                if level_num:
                    current_level = level_num.group(1)

            if current_level and current_level not in spells_by_level:
                spells_by_level[current_level] = set()
            continue

        # Skip school headers and other non-spell lines
        should_skip = False
        for pattern in skip_patterns:
            if pattern.match(line):
                should_skip = True
                break
        if should_skip:
            continue

        # Parse spell entry - first column before tab is the spell name
        if current_level is not None:
            parts = line.split('\t')
            if parts:
                spell_name = parts[0].strip()
                # Clean up spell name - remove trailing race/class markers like "(Orc)", "(Half-Elf)"
                # but keep important markers like "(3.5)" for edition info
                spell_name = re.sub(r'\s*\([A-Z][a-z]+\)\s*$', '', spell_name)
                spell_name = re.sub(r'\s*\([A-Z][a-z]+-[A-Z][a-z]+\)\s*$', '', spell_name)  # Half-Elf etc

                if spell_name and not spell_name.startswith('Spell Name'):
                    spells_by_level[current_level].add(spell_name)

    return spells_by_level


def normalize_spell_name(name: str) -> str:
    """Normalize spell name for comparison."""
    # Convert to lowercase
    name = name.lower()
    # Remove edition markers like (3.5)
    name = re.sub(r'\s*\(3\.5\)\s*', '', name)
    # Remove trailing markers like (AA), (VC)
    name = re.sub(r'\s*\([A-Z]+\)\s*$', '', name)
    # Normalize whitespace
    name = ' '.join(name.split())
    return name


def get_all_spells(spells_by_level: dict[str, set[str]]) -> set[str]:
    """Get all spells across all levels."""
    all_spells = set()
    for spells in spells_by_level.values():
        all_spells.update(spells)
    return all_spells


def compare_lists(druid_spells: dict[str, set[str]], wizard_spells: dict[str, set[str]]):
    """Compare druid and wizard spell lists and print results."""

    # Create normalized lookup maps
    druid_normalized = {}
    for level, spells in druid_spells.items():
        for spell in spells:
            norm = normalize_spell_name(spell)
            if norm not in druid_normalized:
                druid_normalized[norm] = {'name': spell, 'levels': set()}
            druid_normalized[norm]['levels'].add(level)

    wizard_normalized = {}
    for level, spells in wizard_spells.items():
        for spell in spells:
            norm = normalize_spell_name(spell)
            if norm not in wizard_normalized:
                wizard_normalized[norm] = {'name': spell, 'levels': set()}
            wizard_normalized[norm]['levels'].add(level)

    # Find overlaps and unique spells
    druid_only = set(druid_normalized.keys()) - set(wizard_normalized.keys())
    wizard_only = set(wizard_normalized.keys()) - set(druid_normalized.keys())
    both = set(druid_normalized.keys()) & set(wizard_normalized.keys())

    # Helper to get minimum level for sorting
    def min_level(levels: set[str]) -> int:
        return min(int(lvl) for lvl in levels)

    # Print results
    print("=" * 70)
    print("SPELLS ON BOTH LISTS")
    print("=" * 70)
    # Sort by minimum druid level first, then alphabetically
    both_sorted = sorted(both, key=lambda x: (min_level(druid_normalized[x]['levels']), druid_normalized[x]['name']))
    for norm in both_sorted:
        druid_info = druid_normalized[norm]
        wizard_info = wizard_normalized[norm]
        druid_levels = ', '.join(sorted(druid_info['levels']))
        wizard_levels = ', '.join(sorted(wizard_info['levels']))
        print(f"  {druid_info['name']}")
        print(f"    Druid level(s): {druid_levels} | Wizard level(s): {wizard_levels}")
    print(f"\nTotal: {len(both)} spells on both lists")

    print("\n" + "=" * 70)
    print("DRUID-ONLY SPELLS")
    print("=" * 70)
    # Sort by minimum level first, then alphabetically
    druid_only_sorted = sorted(druid_only, key=lambda x: (min_level(druid_normalized[x]['levels']), druid_normalized[x]['name']))
    for norm in druid_only_sorted:
        info = druid_normalized[norm]
        levels = ', '.join(sorted(info['levels']))
        print(f"  {info['name']} (level {levels})")
    print(f"\nTotal: {len(druid_only)} druid-only spells")

    print("\n" + "=" * 70)
    print("WIZARD-ONLY SPELLS")
    print("=" * 70)
    # Sort by minimum level first, then alphabetically
    wizard_only_sorted = sorted(wizard_only, key=lambda x: (min_level(wizard_normalized[x]['levels']), wizard_normalized[x]['name']))
    for norm in wizard_only_sorted:
        info = wizard_normalized[norm]
        levels = ', '.join(sorted(info['levels']))
        print(f"  {info['name']} (level {levels})")
    print(f"\nTotal: {len(wizard_only)} wizard-only spells")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Total unique druid spells (0-2): {len(druid_normalized)}")
    print(f"  Total unique wizard spells (0-2): {len(wizard_normalized)}")
    print(f"  Spells on both lists: {len(both)}")
    print(f"  Druid-only spells: {len(druid_only)}")
    print(f"  Wizard-only spells: {len(wizard_only)}")


def main():
    script_dir = Path(__file__).parent
    druid_file = script_dir / "druid_spells.txt"
    wizard_file = script_dir / "wizard_spells.txt"

    print("Parsing druid spell list...")
    druid_spells = parse_spell_list(druid_file)
    for level, spells in sorted(druid_spells.items()):
        print(f"  Level {level}: {len(spells)} spells")

    print("\nParsing wizard spell list...")
    wizard_spells = parse_spell_list(wizard_file)
    for level, spells in sorted(wizard_spells.items()):
        print(f"  Level {level}: {len(spells)} spells")

    print()
    compare_lists(druid_spells, wizard_spells)


if __name__ == "__main__":
    main()
