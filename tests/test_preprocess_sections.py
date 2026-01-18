"""Unit tests for preprocess_sections.py source name logic."""

import pytest

from preprocess_sections import get_source_name, SOURCE_NAMES, CATEGORY_TEMPLATES, strip_feat_suffix, strip_ability_type_suffix


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


class TestStripFeatSuffix:
    """Tests for strip_feat_suffix() function."""

    def test_combat_suffix(self):
        """Should strip (Combat) suffix."""
        assert strip_feat_suffix("Combat Reflexes (Combat)") == "Combat Reflexes"
        assert strip_feat_suffix("Power Attack (Combat)") == "Power Attack"

    def test_combat_style_suffix(self):
        """Should strip (Combat, Style) suffix."""
        assert strip_feat_suffix("Crane Style (Combat, Style)") == "Crane Style"
        assert strip_feat_suffix("Dragon Style (Combat, Style)") == "Dragon Style"

    def test_achievement_suffix(self):
        """Should strip (Achievement) suffix."""
        assert strip_feat_suffix("Chainbreaker (Achievement)") == "Chainbreaker"
        assert strip_feat_suffix("All Gnolls Must Die (Achievement)") == "All Gnolls Must Die"

    def test_animal_companion_suffix(self):
        """Should strip (Animal Companion Feat) suffix."""
        assert strip_feat_suffix("Curious Companion (Animal Companion Feat)") == "Curious Companion"

    def test_complex_suffixes(self):
        """Should strip multi-part suffixes with semicolons."""
        assert strip_feat_suffix("Feral Grace (Animal Companion Feat; Combat)") == "Feral Grace"
        assert strip_feat_suffix("Ambush Squad (Combat, Teamwork)") == "Ambush Squad"
        assert strip_feat_suffix("Ankle Biter (Combat, Goblin)") == "Ankle Biter"

    def test_no_suffix(self):
        """Titles without suffix should be unchanged."""
        assert strip_feat_suffix("Power Attack") == "Power Attack"
        assert strip_feat_suffix("Improved Initiative") == "Improved Initiative"

    def test_parentheses_in_name(self):
        """Only trailing parentheses should be stripped."""
        # If a feat had parentheses mid-name, they should be preserved
        # (this is hypothetical but tests the regex is anchored to end)
        assert strip_feat_suffix("Some Name (Ex) (Combat)") == "Some Name (Ex)"


class TestStripAbilityTypeSuffix:
    """Tests for strip_ability_type_suffix() function."""

    def test_ex_suffix(self):
        """Should strip (Ex) suffix for extraordinary abilities."""
        assert strip_ability_type_suffix("Flamboyant Arcana (Ex)") == "Flamboyant Arcana"
        assert strip_ability_type_suffix("Accurate Strike (Ex)") == "Accurate Strike"

    def test_su_suffix(self):
        """Should strip (Su) suffix for supernatural abilities."""
        assert strip_ability_type_suffix("Arcane Accuracy (Su)") == "Arcane Accuracy"
        assert strip_ability_type_suffix("Aquatic Agility (Su)") == "Aquatic Agility"

    def test_sp_suffix(self):
        """Should strip (Sp) suffix for spell-like abilities."""
        assert strip_ability_type_suffix("Some Ability (Sp)") == "Some Ability"

    def test_no_suffix(self):
        """Titles without suffix should be unchanged."""
        assert strip_ability_type_suffix("Power Attack") == "Power Attack"
        assert strip_ability_type_suffix("Improved Initiative") == "Improved Initiative"

    def test_other_suffix_unchanged(self):
        """Other parentheticals should NOT be stripped."""
        assert strip_ability_type_suffix("Magic (Greater)") == "Magic (Greater)"
        assert strip_ability_type_suffix("Feat (Combat)") == "Feat (Combat)"
        assert strip_ability_type_suffix("Some Feat (Combat, Style)") == "Some Feat (Combat, Style)"

    def test_case_sensitive(self):
        """Suffix matching should be case-sensitive."""
        assert strip_ability_type_suffix("Ability (ex)") == "Ability (ex)"
        assert strip_ability_type_suffix("Ability (EX)") == "Ability (EX)"
