"""Unit tests for rules lawyer search deduplication."""

import io
import sys

import pytest
from unittest.mock import MagicMock, patch

from pfruleslawyer.rag.rules_lawyer import execute_search, format_context, print_search_results


def make_result(id: str, title: str, source_file: str = "rules/test.md") -> dict:
    """Create a mock search result."""
    return {
        "id": id,
        "title": title,
        "source_file": source_file,
        "source_name": "Test Source",
        "description": f"Description for {title}",
        "content": f"Title: {title}\n\n{title} content here.",
        "score": 0.9,
        "semantic_score": 0.8,
        "keyword_boost": 0.1,
        "subheading_boost": 0.0,
        "title_boost": 0.0,
    }


class TestExecuteSearchDeduplication:
    """Tests for execute_search() deduplication functionality."""

    def test_no_seen_ids_returns_all_results(self):
        """When seen_ids is None, all results should be returned."""
        mock_store = MagicMock()
        mock_store.query.return_value = [
            make_result("test.md::section1", "Section 1"),
            make_result("test.md::section2", "Section 2"),
        ]

        with patch("pfruleslawyer.rag.rules_lawyer.print_search_results"):
            result, new_ids, _ = execute_search("test query", mock_store, seen_ids=None)

        assert "section1" not in result or "Section 1" in result  # Content included
        assert "Section 2" in result
        assert "already retrieved" not in result
        assert len(new_ids) == 2
        assert "test.md::section1" in new_ids
        assert "test.md::section2" in new_ids

    def test_empty_seen_ids_returns_all_results(self):
        """When seen_ids is empty set, all results should be returned."""
        mock_store = MagicMock()
        mock_store.query.return_value = [
            make_result("test.md::section1", "Section 1"),
            make_result("test.md::section2", "Section 2"),
        ]

        with patch("pfruleslawyer.rag.rules_lawyer.print_search_results"):
            result, new_ids, _ = execute_search("test query", mock_store, seen_ids=set())

        assert "already retrieved" not in result
        assert len(new_ids) == 2

    def test_filters_out_seen_ids(self):
        """Results with IDs in seen_ids should be filtered out."""
        mock_store = MagicMock()
        mock_store.query.return_value = [
            make_result("test.md::section1", "Section 1"),
            make_result("test.md::section2", "Section 2"),
            make_result("test.md::section3", "Section 3"),
        ]

        seen_ids = {"test.md::section1", "test.md::section3"}

        with patch("pfruleslawyer.rag.rules_lawyer.print_search_results"):
            result, new_ids, _ = execute_search("test query", mock_store, seen_ids=seen_ids)

        # Only section2 should be in the formatted result
        assert "Section 2" in result
        assert "Section 1" not in result.split("*")[-1]  # Not in content part
        assert "Section 3" not in result.split("*")[-1]
        assert len(new_ids) == 1
        assert "test.md::section2" in new_ids

    def test_shows_dedup_message_when_duplicates_found(self):
        """Should show message about duplicates when some results are filtered."""
        mock_store = MagicMock()
        mock_store.query.return_value = [
            make_result("test.md::section1", "Section 1"),
            make_result("test.md::section2", "Section 2"),
            make_result("test.md::section3", "Section 3"),
        ]

        seen_ids = {"test.md::section1", "test.md::section3"}

        with patch("pfruleslawyer.rag.rules_lawyer.print_search_results"):
            result, new_ids, _ = execute_search("test query", mock_store, seen_ids=seen_ids)

        assert "2 of 3 results already retrieved" in result
        assert "showing 1 new result" in result

    def test_no_dedup_message_when_no_duplicates(self):
        """Should not show dedup message when all results are new."""
        mock_store = MagicMock()
        mock_store.query.return_value = [
            make_result("test.md::section1", "Section 1"),
            make_result("test.md::section2", "Section 2"),
        ]

        seen_ids = {"test.md::other_section"}

        with patch("pfruleslawyer.rag.rules_lawyer.print_search_results"):
            result, new_ids, _ = execute_search("test query", mock_store, seen_ids=seen_ids)

        assert "already retrieved" not in result
        assert len(new_ids) == 2

    def test_all_results_duplicates(self):
        """When all results are duplicates, should show appropriate message."""
        mock_store = MagicMock()
        mock_store.query.return_value = [
            make_result("test.md::section1", "Section 1"),
            make_result("test.md::section2", "Section 2"),
        ]

        seen_ids = {"test.md::section1", "test.md::section2"}

        with patch("pfruleslawyer.rag.rules_lawyer.print_search_results"):
            result, new_ids, _ = execute_search("test query", mock_store, seen_ids=seen_ids)

        assert "2 of 2 results already retrieved" in result
        assert "showing 0 new result" in result
        assert len(new_ids) == 0

    def test_returns_correct_new_ids_for_tracking(self):
        """The returned new_ids should only contain IDs not in seen_ids."""
        mock_store = MagicMock()
        mock_store.query.return_value = [
            make_result("test.md::a", "A"),
            make_result("test.md::b", "B"),
            make_result("test.md::c", "C"),
            make_result("test.md::d", "D"),
        ]

        seen_ids = {"test.md::a", "test.md::c"}

        with patch("pfruleslawyer.rag.rules_lawyer.print_search_results"):
            result, new_ids, _ = execute_search("test query", mock_store, seen_ids=seen_ids)

        assert set(new_ids) == {"test.md::b", "test.md::d"}


class TestPrintSearchResultsDedup:
    """Tests for print_search_results() duplicate marking."""

    def test_marks_duplicates_in_output(self):
        """Duplicate results should be marked with [DUP] in stderr."""
        results = [
            make_result("test.md::section1", "Section 1"),
            make_result("test.md::section2", "Section 2"),
            make_result("test.md::section3", "Section 3"),
        ]
        seen_ids = {"test.md::section1", "test.md::section3"}

        # Capture stderr
        captured = io.StringIO()
        with patch("sys.stderr", captured):
            print_search_results(results, verbose=False, seen_ids=seen_ids)

        output = captured.getvalue()
        assert "[DUP]" in output
        # Should show count of duplicates
        assert "2 duplicate" in output
        assert "1 new" in output

    def test_no_dup_markers_when_no_seen_ids(self):
        """No [DUP] markers when seen_ids is None."""
        results = [
            make_result("test.md::section1", "Section 1"),
        ]

        captured = io.StringIO()
        with patch("sys.stderr", captured):
            print_search_results(results, verbose=False, seen_ids=None)

        output = captured.getvalue()
        assert "[DUP]" not in output

    def test_no_dup_markers_when_all_new(self):
        """No [DUP] markers when all results are new."""
        results = [
            make_result("test.md::section1", "Section 1"),
            make_result("test.md::section2", "Section 2"),
        ]
        seen_ids = {"test.md::other"}

        captured = io.StringIO()
        with patch("sys.stderr", captured):
            print_search_results(results, verbose=False, seen_ids=seen_ids)

        output = captured.getvalue()
        assert "[DUP]" not in output


class TestFormatContext:
    """Tests for format_context() function."""

    def test_formats_multiple_sections(self):
        """Should format multiple sections with separators."""
        results = [
            make_result("test.md::s1", "Section One"),
            make_result("test.md::s2", "Section Two"),
        ]

        formatted = format_context(results)

        assert "### Section One (from Test Source)" in formatted
        assert "### Section Two (from Test Source)" in formatted
        assert "---" in formatted

    def test_respects_max_sections(self):
        """Should respect max_sections limit."""
        results = [
            make_result("test.md::s1", "Section 1"),
            make_result("test.md::s2", "Section 2"),
            make_result("test.md::s3", "Section 3"),
        ]

        formatted = format_context(results, max_sections=2)

        assert "Section 1" in formatted
        assert "Section 2" in formatted
        assert "Section 3" not in formatted

    def test_empty_results(self):
        """Should handle empty results list."""
        formatted = format_context([])
        assert formatted == ""
