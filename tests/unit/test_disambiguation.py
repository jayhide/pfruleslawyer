"""Unit tests for title disambiguation in vector store."""

import pytest
from unittest.mock import MagicMock, patch
import tempfile
import json
from pathlib import Path

from pfruleslawyer.search.vector_store import RulesVectorStore


class TestDisambiguationRules:
    """Tests for disambiguation rules in _find_exact_matches()."""

    @pytest.fixture
    def mock_store(self, tmp_path):
        """Create a RulesVectorStore with mocked indices."""
        # Create a temp config file with disambiguation rules
        config = {
            "disambiguation_rules": {
                "medium": {
                    "negative_contexts": [
                        "medium armor",
                        "medium size",
                        "size medium",
                        "medium creature",
                        "medium load",
                        "medium range",
                        "medium-size"
                    ]
                }
            },
            "category_weights": {}
        }
        config_path = tmp_path / "preprocess_config.json"
        with open(config_path, "w") as f:
            json.dump(config, f)

        # Create store with mocked paths
        with patch.object(RulesVectorStore, '__init__', lambda self, **kwargs: None):
            store = RulesVectorStore()
            store._config_path = config_path
            store._category_weights = None
            store._disambiguation_rules = None

            # Set up mock indices
            store._keyword_index = {}
            store._subheading_index = {}
            store._title_index = {
                "medium": ["archetype::medium"],
                "armor": ["rules::armor"],
                "medium armor": ["rules::medium-armor-section"],
            }
            store._section_metadata = {
                "archetype::medium": {"title": "Medium", "category": "Archetypes"},
                "rules::armor": {"title": "Armor", "category": "Core Rules"},
                "rules::medium-armor-section": {"title": "Medium Armor", "category": "Core Rules"},
            }

        return store

    def test_negative_context_suppresses_title_match(self, mock_store):
        """Query containing 'medium armor' should NOT match 'medium' archetype."""
        matches = mock_store._find_exact_matches("What bonuses does medium armor give?")

        # Should NOT have archetype::medium in matches (or it should have 0 title_matches)
        if "archetype::medium" in matches:
            assert matches["archetype::medium"]["title_matches"] == 0

    def test_no_negative_context_allows_title_match(self, mock_store):
        """Query about 'the Medium' should match the Medium archetype."""
        matches = mock_store._find_exact_matches("How does the Medium class work?")

        # Should have archetype::medium with title_matches > 0
        assert "archetype::medium" in matches
        assert matches["archetype::medium"]["title_matches"] > 0

    def test_medium_creature_suppresses_match(self, mock_store):
        """Query about 'medium creature' should NOT match Medium archetype."""
        matches = mock_store._find_exact_matches("Can a medium creature grapple a large one?")

        if "archetype::medium" in matches:
            assert matches["archetype::medium"]["title_matches"] == 0

    def test_standalone_medium_matches(self, mock_store):
        """Query with just 'medium' should match the archetype."""
        matches = mock_store._find_exact_matches("Tell me about the Medium")

        assert "archetype::medium" in matches
        assert matches["archetype::medium"]["title_matches"] > 0

    def test_medium_size_suppresses_match(self, mock_store):
        """Query about 'medium size' should NOT match Medium archetype."""
        matches = mock_store._find_exact_matches("What weapons can medium size creatures use?")

        if "archetype::medium" in matches:
            assert matches["archetype::medium"]["title_matches"] == 0

    def test_case_insensitive_negative_context(self, mock_store):
        """Negative context matching should be case-insensitive."""
        matches = mock_store._find_exact_matches("MEDIUM ARMOR proficiency")

        if "archetype::medium" in matches:
            assert matches["archetype::medium"]["title_matches"] == 0

    def test_hyphenated_negative_context(self, mock_store):
        """Should detect hyphenated negative context like 'medium-size'."""
        matches = mock_store._find_exact_matches("A medium-size humanoid attacks")

        if "archetype::medium" in matches:
            assert matches["archetype::medium"]["title_matches"] == 0

    def test_other_titles_unaffected(self, mock_store):
        """Disambiguation rules should only affect the specified title."""
        matches = mock_store._find_exact_matches("What is medium armor?")

        # 'armor' title should still match
        assert "rules::armor" in matches
        assert matches["rules::armor"]["title_matches"] > 0

    def test_multi_word_title_still_matches(self, mock_store):
        """Multi-word title 'medium armor' should still match when queried directly."""
        matches = mock_store._find_exact_matches("Tell me about medium armor")

        # The exact title "medium armor" should match
        assert "rules::medium-armor-section" in matches
        assert matches["rules::medium-armor-section"]["title_matches"] > 0


class TestDisambiguationConfigLoading:
    """Tests for loading disambiguation rules from config."""

    def test_loads_rules_from_config(self, tmp_path):
        """Should load disambiguation_rules from config file."""
        config = {
            "disambiguation_rules": {
                "test": {"negative_contexts": ["test context"]}
            },
            "category_weights": {}
        }
        config_path = tmp_path / "config.json"
        with open(config_path, "w") as f:
            json.dump(config, f)

        with patch.object(RulesVectorStore, '__init__', lambda self, **kwargs: None):
            store = RulesVectorStore()
            store._config_path = config_path
            store._category_weights = None
            store._disambiguation_rules = None

            store._load_category_weights()

            assert store._disambiguation_rules == {"test": {"negative_contexts": ["test context"]}}

    def test_defaults_to_empty_dict_when_missing(self, tmp_path):
        """Should default to empty dict when disambiguation_rules not in config."""
        config = {"category_weights": {}}
        config_path = tmp_path / "config.json"
        with open(config_path, "w") as f:
            json.dump(config, f)

        with patch.object(RulesVectorStore, '__init__', lambda self, **kwargs: None):
            store = RulesVectorStore()
            store._config_path = config_path
            store._category_weights = None
            store._disambiguation_rules = None

            store._load_category_weights()

            assert store._disambiguation_rules == {}

    def test_defaults_when_config_missing(self, tmp_path):
        """Should default to empty dict when config file doesn't exist."""
        config_path = tmp_path / "nonexistent.json"

        with patch.object(RulesVectorStore, '__init__', lambda self, **kwargs: None):
            store = RulesVectorStore()
            store._config_path = config_path
            store._category_weights = None
            store._disambiguation_rules = None

            store._load_category_weights()

            assert store._disambiguation_rules == {}
