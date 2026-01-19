"""Extract section content from markdown files using manifest definitions."""

import json
import re
from pathlib import Path

from pfruleslawyer.core import HtmlCacheDB, Section


def strip_anchor_id(text: str) -> tuple[str, str | None]:
    """Strip {#anchor-id} suffix from heading text.

    Args:
        text: Heading text, possibly with {#id} suffix

    Returns:
        Tuple of (text_without_anchor, anchor_id or None)
    """
    match = re.match(r'^(.+?)\s*\{#([^}]+)\}\s*$', text)
    if match:
        return match.group(1).strip(), match.group(2)
    return text, None


def get_heading_level(line: str) -> int | None:
    """Get the heading level (1-6) from a markdown line, or None if not a heading.

    Handles both plain headings and headings with {#id} suffix.

    Args:
        line: A line of markdown text

    Returns:
        The heading level (1-6) or None if not a heading
    """
    match = re.match(r'^(#{1,6})\s+', line)
    if match:
        return len(match.group(1))
    return None


def extract_section_content(
    markdown: str,
    anchor_heading: str,
    end_at_heading: str | None = None
) -> str | None:
    """Extract content for a section starting at the anchor heading.

    Extracts all content from the anchor heading until the next heading
    at the same or higher level (fewer # symbols), or until end_at_heading
    if specified.

    Args:
        markdown: The full markdown content
        anchor_heading: The exact heading text to find (e.g., "### Initiative")
        end_at_heading: Optional heading text to stop at (for bounded sections)

    Returns:
        The section content including the heading, or None if not found
    """
    lines = markdown.split('\n')

    # Parse the anchor heading to get its level
    anchor_level = get_heading_level(anchor_heading)
    if anchor_level is None:
        return None

    # Normalize the anchor heading for comparison (strip {#id} suffix)
    anchor_text = anchor_heading.lstrip('#').strip()
    anchor_text, _ = strip_anchor_id(anchor_text)

    # Parse end_at_heading if provided
    end_at_text = None
    end_at_level = None
    if end_at_heading:
        end_at_level = get_heading_level(end_at_heading)
        end_at_text = end_at_heading.lstrip('#').strip()
        end_at_text, _ = strip_anchor_id(end_at_text)

    # Find the start of the section
    start_idx = None
    for i, line in enumerate(lines):
        line_level = get_heading_level(line)
        if line_level is not None:
            line_text = line.lstrip('#').strip()
            # Strip anchor ID suffix for comparison (handles {#id} syntax)
            line_text_clean, _ = strip_anchor_id(line_text)
            if line_text_clean == anchor_text and line_level == anchor_level:
                start_idx = i
                break

    if start_idx is None:
        return None

    # Find the end of the section
    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        line_level = get_heading_level(lines[i])
        if line_level is not None:
            line_text = lines[i].lstrip('#').strip()
            line_text_clean, _ = strip_anchor_id(line_text)

            # Check for end_at_heading match
            if end_at_text and line_text_clean == end_at_text:
                if end_at_level is None or line_level == end_at_level:
                    end_idx = i
                    break

            # Check for same or higher level heading
            if line_level <= anchor_level:
                end_idx = i
                break

    # Extract and return the content
    section_lines = lines[start_idx:end_idx]
    content = '\n'.join(section_lines).strip()

    return content


# Default paths relative to project root
DEFAULT_RULES_DIR = Path(__file__).parent.parent.parent.parent / "rules"
DEFAULT_MANIFESTS_DIR = Path(__file__).parent.parent.parent.parent / "data" / "manifests"


class SectionExtractor:
    """Extracts sections from markdown files using manifest definitions."""

    def __init__(
        self,
        rules_dir: str | Path | None = None,
        manifests_dir: str | Path | None = None,
        db: HtmlCacheDB | None = None
    ):
        """Initialize the extractor.

        Args:
            rules_dir: Directory containing markdown rules files (legacy)
            manifests_dir: Directory containing manifest JSON files
            db: Database instance for fetching markdown from URLs
        """
        self.rules_dir = Path(rules_dir) if rules_dir else DEFAULT_RULES_DIR
        self.manifests_dir = Path(manifests_dir) if manifests_dir else DEFAULT_MANIFESTS_DIR
        self.db = db or HtmlCacheDB()
        self._sections: list[Section] | None = None
        self._markdown_cache: dict[str, str] = {}

    def _load_markdown(self, source_path: str) -> str:
        """Load and cache markdown content.

        Args:
            source_path: URL or file path. URLs are fetched from the database,
                        file paths are read from the filesystem.
        """
        if source_path not in self._markdown_cache:
            # Check if source_path is a URL
            if source_path.startswith("http://") or source_path.startswith("https://"):
                # Fetch from database
                markdown = self.db.get_markdown(source_path)
                if markdown is None:
                    raise FileNotFoundError(f"No markdown found in database for URL: {source_path}")
                self._markdown_cache[source_path] = markdown
            else:
                # Legacy: read from filesystem
                filepath = Path(source_path)
                if not filepath.exists():
                    # Try relative to rules_dir parent (project root)
                    filepath = self.rules_dir.parent / source_path
                self._markdown_cache[source_path] = filepath.read_text(encoding="utf-8")
        return self._markdown_cache[source_path]

    def _load_manifest(self, manifest_path: Path) -> dict:
        """Load a manifest JSON file."""
        with open(manifest_path, encoding="utf-8") as f:
            return json.load(f)

    def load_all_sections(self) -> list[Section]:
        """Load all sections from all manifests.

        Returns:
            List of all Section objects
        """
        if self._sections is not None:
            return self._sections

        self._sections = []

        for manifest_path in sorted(self.manifests_dir.glob("**/*.json")):
            manifest = self._load_manifest(manifest_path)
            source_file = manifest["file"]
            source_path = manifest.get("source_path", f"rules/{source_file}")
            # Fallback to title-cased filename if source_name not in manifest
            source_name = manifest.get("source_name")
            if not source_name:
                source_name = source_file.replace(".md", "").replace("-", " ").title()
            # Get category for search weight customization (default to Uncategorized)
            category = manifest.get("category", "Uncategorized")
            markdown = self._load_markdown(source_path)

            # Check for TOC content (used for class documents)
            toc_content = manifest.get("toc_content", "")

            # Extract class name from source_name for TOC header (e.g., "Class: Magus" -> "Magus")
            class_name = None
            if toc_content and source_name and source_name.startswith("Class: "):
                class_name = source_name[7:]  # Strip "Class: " prefix

            for section_def in manifest["sections"]:
                # Extract content with optional end_at_heading
                end_at = section_def.get("end_at_heading")
                content = extract_section_content(
                    markdown,
                    section_def["anchor_heading"],
                    end_at_heading=end_at
                )

                if content is None:
                    print(f"Warning: Could not find section '{section_def['id']}' "
                          f"with anchor '{section_def['anchor_heading']}' in {source_path}")
                    continue

                # Prepend TOC for class documents
                if toc_content and class_name:
                    toc_header = f"## {class_name} Table of Contents\n\n{toc_content}\n\n---\n\n"
                    content = toc_header + content

                section = Section(
                    id=section_def["id"],
                    title=section_def["title"],
                    description=section_def["description"],
                    keywords=section_def["keywords"],
                    content=content,
                    source_file=source_path,
                    source_name=source_name,
                    anchor_heading=section_def["anchor_heading"],
                    category=category
                )
                self._sections.append(section)

        return self._sections

    def get_section_by_id(self, section_id: str) -> Section | None:
        """Get a specific section by its ID.

        Args:
            section_id: The unique section identifier

        Returns:
            The Section or None if not found
        """
        sections = self.load_all_sections()
        for section in sections:
            if section.id == section_id:
                return section
        return None

    def search_by_keyword(self, keyword: str) -> list[Section]:
        """Find sections that have a matching keyword.

        Args:
            keyword: The keyword to search for (case-insensitive)

        Returns:
            List of matching sections
        """
        keyword = keyword.lower()
        sections = self.load_all_sections()
        return [s for s in sections if keyword in [k.lower() for k in s.keywords]]

    def search_by_text(self, query: str) -> list[Section]:
        """Find sections where the query appears in title, description, or keywords.

        Args:
            query: The text to search for (case-insensitive)

        Returns:
            List of matching sections
        """
        query = query.lower()
        sections = self.load_all_sections()
        results = []

        for section in sections:
            if (query in section.title.lower() or
                query in section.description.lower() or
                any(query in k.lower() for k in section.keywords)):
                results.append(section)

        return results

    def get_sections_for_file(self, filename: str) -> list[Section]:
        """Get all sections from a specific source file.

        Args:
            filename: The source markdown filename (e.g., "combat.md")

        Returns:
            List of sections from that file
        """
        sections = self.load_all_sections()
        return [s for s in sections if s.source_file == filename]
