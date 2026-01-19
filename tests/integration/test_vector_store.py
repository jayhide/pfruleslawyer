"""Tests for vector_store search retrieval accuracy.

This test suite verifies that search queries return expected sections.
Add new test cases as failing searches are discovered.

Run with: poetry run pytest tests/integration/test_vector_store.py -v
"""

import pytest

from pfruleslawyer.search import RulesVectorStore


@pytest.fixture(scope="module")
def store():
    """Module-scoped fixture to avoid reloading vector store for each test."""
    return RulesVectorStore()


def assert_retrieved(
    results: list[dict],
    *,
    section_id: str | None = None,
    title_contains: str | None = None,
    source_contains: str | None = None,
    top_n: int | None = None,
):
    """Assert that a section matching criteria appears in results.

    Args:
        results: Query results from store.query()
        section_id: Exact section ID to find
        title_contains: Substring that must appear in title (case-insensitive)
        source_contains: Substring that must appear in source_name (case-insensitive)
        top_n: If set, section must appear in top N results; if None, anywhere

    Raises:
        AssertionError: If no matching section is found in results
    """
    if top_n is not None:
        search_results = results[:top_n]
        location_desc = f"top {top_n}"
    else:
        search_results = results
        location_desc = "results"

    for result in search_results:
        matches = True

        if section_id is not None and result["id"] != section_id:
            matches = False
        if title_contains is not None and title_contains.lower() not in result["title"].lower():
            matches = False
        if source_contains is not None and source_contains.lower() not in result.get("source_name", "").lower():
            matches = False

        if matches:
            return  # Found a matching result

    # Build error message
    criteria = []
    if section_id:
        criteria.append(f"section_id={section_id!r}")
    if title_contains:
        criteria.append(f"title_contains={title_contains!r}")
    if source_contains:
        criteria.append(f"source_contains={source_contains!r}")

    actual_results = [f"  {i+1}. {r['title']} (id={r['id']})" for i, r in enumerate(search_results)]
    actual_str = "\n".join(actual_results) if actual_results else "  (no results)"

    raise AssertionError(
        f"No section matching {', '.join(criteria)} found in {location_desc}.\n"
        f"Actual results:\n{actual_str}"
    )


class TestTitleMatching:
    """Tests for exact title/keyword matching."""

    def test_exact_spell_name_fireball(self, store):
        """Searching 'fireball' should return the Fireball spell."""
        results = store.query("fireball", n_results=10)
        assert_retrieved(results, title_contains="Fireball", top_n=5)

    def test_grapple_keyword(self, store):
        """Searching 'grapple' should return grapple-related rules."""
        results = store.query("grapple", n_results=10)
        assert_retrieved(results, title_contains="Grapple", top_n=5)


class TestSemanticSearch:
    """Tests for semantic/conceptual query matching."""

    def test_how_does_grappling_work(self, store):
        """Searching 'how does grappling work' should return grapple rules."""
        results = store.query("how does grappling work", n_results=10)
        assert_retrieved(results, title_contains="Grapple", top_n=5)

    def test_attack_of_opportunity(self, store):
        """Searching 'attack of opportunity' should return AoO rules."""
        results = store.query("attack of opportunity", n_results=10)
        assert_retrieved(results, title_contains="Opportunity", top_n=5)


class TestRegressionCases:
    """Specific search cases that previously returned wrong results.

    Add new tests here as failing cases are discovered.
    """

    def test_flamboyant_arcana_without_suffix(self, store):
        """Searching 'flamboyant arcana' should find the magus arcana.

        Regression test: titles were stored with (Ex)/(Sp)/(Su) suffixes,
        preventing matches when users searched without the suffix.
        """
        results = store.query("flamboyant arcana", n_results=10)
        assert_retrieved(results, title_contains="Flamboyant Arcana", top_n=5)
