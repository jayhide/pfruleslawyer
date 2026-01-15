"""Unit tests for preprocess_sections.py source name logic."""

import pytest

from preprocess_sections import get_source_name, SOURCE_NAMES, CATEGORY_TEMPLATES


class TestGetSourceName:
    """Tests for get_source_name() function."""

    def test_top_level_mapped_files(self):
        """Files in SOURCE_NAMES should return their mapped names."""
        assert get_source_name("rules/combat.md") == "Combat Rules"
        assert get_source_name("rules/conditions.md") == "Conditions"
        assert get_source_name("rules/magic.md") == "Magic Rules"
        assert get_source_name("rules/skills.md") == "Skills Overview"
        assert get_source_name("rules/afflictions.md") == "Afflictions (Curses, Diseases, Poisons)"
        assert get_source_name("rules/creature-types.md") == "Creature Types & Subtypes"

    def test_all_source_names_mapped(self):
        """All entries in SOURCE_NAMES should be retrievable."""
        for filename, expected_name in SOURCE_NAMES.items():
            source_path = f"rules/{filename}"
            assert get_source_name(source_path) == expected_name

    def test_skill_category_template(self):
        """Skills in subdirectory should use 'Skill: Name' format."""
        assert get_source_name("rules/skills/acrobatics.md") == "Skill: Acrobatics"
        assert get_source_name("rules/skills/perception.md") == "Skill: Perception"
        assert get_source_name("rules/skills/sense-motive.md") == "Skill: Sense Motive"
        assert get_source_name("rules/skills/use-magic-device.md") == "Skill: Use Magic Device"

    def test_spell_category_template(self):
        """Spells in subdirectory should use 'Spell: Name' format."""
        assert get_source_name("rules/spells/fireball.md") == "Spell: Fireball"
        assert get_source_name("rules/spells/magic-missile.md") == "Spell: Magic Missile"
        assert get_source_name("rules/spells/cure-light-wounds.md") == "Spell: Cure Light Wounds"

    def test_feat_category_template(self):
        """Feats in subdirectory should use 'Feat: Name' format."""
        assert get_source_name("rules/feats/power-attack.md") == "Feat: Power Attack"
        assert get_source_name("rules/feats/combat-reflexes.md") == "Feat: Combat Reflexes"
        assert get_source_name("rules/feats/improved-initiative.md") == "Feat: Improved Initiative"

    def test_all_category_templates(self):
        """All entries in CATEGORY_TEMPLATES should work."""
        for subdir, category in CATEGORY_TEMPLATES.items():
            source_path = f"rules/{subdir}/test-item.md"
            assert get_source_name(source_path) == f"{category}: Test Item"

    def test_unmapped_top_level_file_fallback(self):
        """Unmapped top-level files should fallback to title-cased filename."""
        assert get_source_name("rules/unknown-file.md") == "Unknown File"
        assert get_source_name("rules/new-rules.md") == "New Rules"
        assert get_source_name("rules/simple.md") == "Simple"

    def test_unknown_subdirectory_fallback(self):
        """Files in unknown subdirectories should fallback to title-cased filename."""
        assert get_source_name("rules/unknown/some-file.md") == "Some File"
        assert get_source_name("rules/other/test.md") == "Test"

    def test_deeply_nested_paths(self):
        """Deeply nested paths should still detect category from parent dir."""
        # Category detection uses parts[-2], so this should work
        assert get_source_name("some/path/rules/skills/stealth.md") == "Skill: Stealth"

    def test_windows_style_paths(self):
        """Windows-style backslash paths should be handled."""
        assert get_source_name("rules\\skills\\acrobatics.md") == "Skill: Acrobatics"
        assert get_source_name("rules\\combat.md") == "Combat Rules"

    def test_hyphenated_names_title_cased(self):
        """Hyphenated filenames should become properly title-cased."""
        assert get_source_name("rules/skills/disable-device.md") == "Skill: Disable Device"
        assert get_source_name("rules/skills/handle-animal.md") == "Skill: Handle Animal"

    def test_short_paths(self):
        """Very short paths should fallback gracefully."""
        assert get_source_name("combat.md") == "Combat Rules"
        assert get_source_name("unknown.md") == "Unknown"

    def test_path_with_only_filename(self):
        """Path with just filename should check SOURCE_NAMES."""
        assert get_source_name("magic.md") == "Magic Rules"
        assert get_source_name("conditions.md") == "Conditions"
