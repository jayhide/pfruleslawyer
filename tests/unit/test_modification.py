"""Unit tests for the modification module."""

import pytest

from pfruleslawyer.modification.operations import (
    remove_section,
    remove_lines,
    remove_text,
    replace_text,
    apply_operation,
)
from pfruleslawyer.modification import MarkdownModifier


class TestRemoveSection:
    """Tests for remove_section operation."""

    def test_remove_section_basic(self):
        """Remove a section until next same-level heading."""
        markdown = """# Title

## Section One

Content for section one.

## Section Two

Content for section two.

## Section Three

Content for section three.
"""
        result, change = remove_section(markdown, "## Section Two")
        assert "## Section Two" not in result
        assert "Content for section two" not in result
        assert "## Section One" in result
        assert "## Section Three" in result
        assert change is not None
        assert "Section Two" in change

    def test_remove_section_with_end_heading(self):
        """Remove a section until specific end heading."""
        markdown = """# Title

## Start

Content to remove.

### Subsection

More content to remove.

## End

Content to keep.
"""
        result, change = remove_section(markdown, "## Start", "## End")
        assert "## Start" not in result
        assert "Content to remove" not in result
        assert "### Subsection" not in result
        assert "## End" in result
        assert "Content to keep" in result

    def test_remove_section_not_found(self):
        """Return unchanged if heading not found."""
        markdown = "# Title\n\n## Other Section\n\nContent"
        result, change = remove_section(markdown, "## Missing Section")
        assert result == markdown
        assert change is None

    def test_remove_section_with_anchor_id(self):
        """Handle headings with {#id} suffix."""
        markdown = """# Title

## Section One {#section-one}

Content for section one.

## Section Two {#section-two}

Content for section two.
"""
        result, change = remove_section(markdown, "## Section One")
        assert "Section One" not in result
        assert "Content for section one" not in result
        assert "## Section Two" in result

    def test_remove_section_nested_headings(self):
        """Only stop at same or higher level headings."""
        markdown = """# Title

## Main Section

Content.

### Subsection

Subsection content.

#### Deep Section

Deep content.

## Next Main

Next content.
"""
        result, change = remove_section(markdown, "## Main Section")
        assert "## Main Section" not in result
        assert "### Subsection" not in result
        assert "#### Deep Section" not in result
        assert "## Next Main" in result
        assert "Next content" in result


class TestRemoveLines:
    """Tests for remove_lines operation."""

    def test_remove_lines_basic(self):
        """Remove lines matching a simple pattern."""
        markdown = "Line one\nSource: 3pp content\nLine three\n"
        result, change = remove_lines(markdown, r"Source:.*3pp")
        assert "Source: 3pp" not in result
        assert "Line one" in result
        assert "Line three" in result
        assert "1 lines" in change

    def test_remove_lines_multiple(self):
        """Remove multiple matching lines."""
        markdown = "Keep\nRemove me\nKeep\nRemove me too\nKeep\n"
        result, change = remove_lines(markdown, r"Remove")
        assert "Remove" not in result
        assert result.count("Keep") == 3
        assert "2 lines" in change

    def test_remove_lines_no_match(self):
        """Return unchanged if no matches."""
        markdown = "Line one\nLine two\n"
        result, change = remove_lines(markdown, r"nonexistent")
        assert result == markdown
        assert change is None


class TestRemoveText:
    """Tests for remove_text operation."""

    def test_remove_text_basic(self):
        """Remove exact text occurrences."""
        markdown = "Hello [Show][Hide] world [Show][Hide] end"
        result, change = remove_text(markdown, "[Show][Hide]")
        assert "[Show][Hide]" not in result
        assert "Hello  world  end" == result
        assert "2 occurrence" in change

    def test_remove_text_not_found(self):
        """Return unchanged if text not found."""
        markdown = "Hello world"
        result, change = remove_text(markdown, "xyz")
        assert result == markdown
        assert change is None


class TestReplaceText:
    """Tests for replace_text operation."""

    def test_replace_text_basic(self):
        """Basic regex replacement."""
        markdown = "Version 1.0 and Version 2.0"
        result, change = replace_text(markdown, r"Version (\d+\.\d+)", r"v\1")
        assert result == "v1.0 and v2.0"
        assert "2 match" in change

    def test_replace_text_multiline(self):
        """Replace across multiple matches with DOTALL."""
        markdown = "Start [show]hidden[/show] end"
        result, change = replace_text(markdown, r"\[show\].*?\[/show\]", "")
        assert result == "Start  end"

    def test_replace_text_no_match(self):
        """Return unchanged if no matches."""
        markdown = "Hello world"
        result, change = replace_text(markdown, r"xyz\d+", "abc")
        assert result == markdown
        assert change is None


class TestApplyOperation:
    """Tests for apply_operation dispatcher."""

    def test_apply_remove_section(self):
        """Apply remove_section operation."""
        markdown = "# Title\n\n## Remove\n\nContent\n\n## Keep\n\nKept"
        op = {"type": "remove_section", "start_heading": "## Remove"}
        result, change = apply_operation(markdown, op)
        assert "## Remove" not in result
        assert "## Keep" in result

    def test_apply_remove_lines(self):
        """Apply remove_lines operation."""
        markdown = "Keep\nRemove: 3pp\nKeep"
        op = {"type": "remove_lines", "pattern": r"3pp"}
        result, change = apply_operation(markdown, op)
        assert "3pp" not in result

    def test_apply_remove_text(self):
        """Apply remove_text operation."""
        markdown = "Hello [x] world"
        op = {"type": "remove_text", "text": "[x]"}
        result, change = apply_operation(markdown, op)
        assert "[x]" not in result

    def test_apply_replace(self):
        """Apply replace operation."""
        markdown = "foo bar"
        op = {"type": "replace", "pattern": "foo", "replacement": "baz"}
        result, change = apply_operation(markdown, op)
        assert result == "baz bar"

    def test_apply_unknown_type(self):
        """Raise error for unknown operation type."""
        with pytest.raises(ValueError, match="Unknown operation type"):
            apply_operation("content", {"type": "unknown"})

    def test_apply_missing_type(self):
        """Raise error for missing type field."""
        with pytest.raises(ValueError, match="missing 'type'"):
            apply_operation("content", {})

    def test_apply_missing_required_param(self):
        """Raise error for missing required parameters."""
        with pytest.raises(ValueError, match="requires 'start_heading'"):
            apply_operation("content", {"type": "remove_section"})


class TestMarkdownModifier:
    """Tests for MarkdownModifier class."""

    def test_no_modifications(self):
        """Return original content when no modifications configured."""
        modifier = MarkdownModifier(config=[])
        # Use a mock-like approach - just test the logic
        assert modifier.has_modifications("https://example.com") is False

    def test_url_matching(self):
        """Match exact URLs."""
        config = [
            {
                "url": "https://example.com/page",
                "operations": [{"type": "remove_text", "text": "remove"}]
            }
        ]
        modifier = MarkdownModifier(config=config)
        assert modifier.has_modifications("https://example.com/page") is True
        assert modifier.has_modifications("https://example.com/other") is False

    def test_pattern_matching(self):
        """Match URL patterns."""
        config = [
            {
                "pattern": "https://example.com/feats/*",
                "operations": [{"type": "remove_text", "text": "remove"}]
            }
        ]
        modifier = MarkdownModifier(config=config)
        assert modifier.has_modifications("https://example.com/feats/power-attack") is True
        assert modifier.has_modifications("https://example.com/spells/fireball") is False

    def test_get_all_modified_urls(self):
        """List all configured modifications."""
        config = [
            {"url": "https://example.com/a", "operations": [{"type": "remove_text", "text": "x"}]},
            {"pattern": "https://example.com/b/*", "operations": [
                {"type": "remove_text", "text": "y"},
                {"type": "remove_text", "text": "z"}
            ]},
        ]
        modifier = MarkdownModifier(config=config)
        entries = modifier.get_all_modified_urls()

        assert len(entries) == 2
        assert entries[0]["url"] == "https://example.com/a"
        assert entries[0]["operation_count"] == 1
        assert entries[1]["pattern"] == "https://example.com/b/*"
        assert entries[1]["operation_count"] == 2
