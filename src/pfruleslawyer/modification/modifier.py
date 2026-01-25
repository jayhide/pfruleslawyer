"""MarkdownModifier class for applying configuration-driven transformations."""

import fnmatch
import re
from pathlib import Path

import yaml

from pfruleslawyer.core import HtmlCacheDB
from .operations import apply_operation


# Default config path relative to this file
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "config" / "markdown_modifications.yaml"


class MarkdownModifier:
    """Applies configured modifications to markdown content.

    Wraps database access to apply transformations before preprocessing,
    while keeping the original database content unchanged.
    """

    def __init__(self, config: list | None = None, config_path: Path | None = None):
        """Initialize with modification config.

        Args:
            config: List of modification entries (url/pattern + operations).
                   If None, loads from config file.
            config_path: Path to config file. Defaults to preprocess_config.yaml.
        """
        if config is not None:
            self._modifications = config
        else:
            self._modifications = self._load_modifications(config_path or DEFAULT_CONFIG_PATH)

    def _load_modifications(self, config_path: Path) -> list:
        """Load modifications from config file."""
        if not config_path.exists():
            return []

        with open(config_path) as f:
            config = yaml.safe_load(f)

        if not config:
            return []

        return config.get("modifications") or []

    def _url_matches_pattern(self, url: str, pattern: str) -> bool:
        """Check if URL matches a glob pattern."""
        regex_pattern = fnmatch.translate(pattern)
        return bool(re.match(regex_pattern, url))

    def _get_operations_for_url(self, url: str) -> list[dict]:
        """Get all operations that apply to a given URL.

        Returns operations from all matching entries (exact url or pattern match).
        """
        operations = []

        for entry in self._modifications:
            matches = False

            if "url" in entry:
                # Exact URL match
                matches = entry["url"] == url
            elif "pattern" in entry:
                # Pattern match
                matches = self._url_matches_pattern(url, entry["pattern"])

            if matches:
                operations.extend(entry.get("operations", []))

        return operations

    def _apply_operations(
        self,
        markdown: str,
        operations: list[dict]
    ) -> tuple[str, list[str]]:
        """Apply a list of operations to markdown content.

        Args:
            markdown: The markdown content to modify
            operations: List of operation dicts

        Returns:
            Tuple of (modified_markdown, list_of_change_descriptions)
        """
        changes = []
        result = markdown

        for operation in operations:
            result, change_desc = apply_operation(result, operation)
            if change_desc:
                changes.append(change_desc)

        return result, changes

    def get_markdown(self, db: HtmlCacheDB, url: str) -> str | None:
        """Get markdown with modifications applied.

        Args:
            db: Database instance to fetch original markdown
            url: URL to fetch markdown for

        Returns:
            Modified markdown content, or None if not found
        """
        markdown = db.get_markdown(url)
        if markdown is None:
            return None

        operations = self._get_operations_for_url(url)
        if not operations:
            return markdown

        modified, _ = self._apply_operations(markdown, operations)
        return modified

    def preview(self, db: HtmlCacheDB, url: str) -> tuple[str | None, str | None, list[str]]:
        """Preview modifications for a URL.

        Args:
            db: Database instance to fetch original markdown
            url: URL to preview modifications for

        Returns:
            Tuple of (original_markdown, modified_markdown, change_log)
            Returns (None, None, []) if URL not found in database
        """
        original = db.get_markdown(url)
        if original is None:
            return None, None, []

        operations = self._get_operations_for_url(url)
        if not operations:
            return original, original, []

        modified, changes = self._apply_operations(original, operations)
        return original, modified, changes

    def has_modifications(self, url: str) -> bool:
        """Check if a URL has any configured modifications."""
        return len(self._get_operations_for_url(url)) > 0

    def get_all_modified_urls(self) -> list[dict]:
        """Get all URLs/patterns with configured modifications.

        Returns:
            List of dicts with 'url' or 'pattern' and 'operation_count' keys
        """
        result = []
        for entry in self._modifications:
            info = {"operation_count": len(entry.get("operations", []))}
            if "url" in entry:
                info["url"] = entry["url"]
            elif "pattern" in entry:
                info["pattern"] = entry["pattern"]
            result.append(info)
        return result
