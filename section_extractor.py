"""Extract section content from markdown files using manifest definitions."""

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Section:
    """A section of rules content extracted from markdown."""
    id: str
    title: str
    description: str
    keywords: list[str]
    content: str
    source_file: str
    anchor_heading: str

    def __repr__(self) -> str:
        content_preview = self.content[:100] + "..." if len(self.content) > 100 else self.content
        return f"Section(id={self.id!r}, title={self.title!r}, content={content_preview!r})"


def get_heading_level(line: str) -> int | None:
    """Get the heading level (1-6) from a markdown line, or None if not a heading.

    Args:
        line: A line of markdown text

    Returns:
        The heading level (1-6) or None if not a heading
    """
    match = re.match(r'^(#{1,6})\s+', line)
    if match:
        return len(match.group(1))
    return None


def extract_section_content(markdown: str, anchor_heading: str) -> str | None:
    """Extract content for a section starting at the anchor heading.

    Extracts all content from the anchor heading until the next heading
    at the same or higher level (fewer # symbols).

    Args:
        markdown: The full markdown content
        anchor_heading: The exact heading text to find (e.g., "### Initiative")

    Returns:
        The section content including the heading, or None if not found
    """
    lines = markdown.split('\n')

    # Parse the anchor heading to get its level
    anchor_level = get_heading_level(anchor_heading)
    if anchor_level is None:
        return None

    # Normalize the anchor heading for comparison
    anchor_text = anchor_heading.lstrip('#').strip()

    # Find the start of the section
    start_idx = None
    for i, line in enumerate(lines):
        line_level = get_heading_level(line)
        if line_level is not None:
            line_text = line.lstrip('#').strip()
            if line_text == anchor_text and line_level == anchor_level:
                start_idx = i
                break

    if start_idx is None:
        return None

    # Find the end of the section (next heading at same or higher level)
    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        line_level = get_heading_level(lines[i])
        if line_level is not None and line_level <= anchor_level:
            end_idx = i
            break

    # Extract and return the content
    section_lines = lines[start_idx:end_idx]
    content = '\n'.join(section_lines).strip()

    return content


class SectionExtractor:
    """Extracts sections from markdown files using manifest definitions."""

    def __init__(self, rules_dir: str | Path = "rules", manifests_dir: str | Path = "manifests"):
        """Initialize the extractor.

        Args:
            rules_dir: Directory containing markdown rules files
            manifests_dir: Directory containing manifest JSON files
        """
        self.rules_dir = Path(rules_dir)
        self.manifests_dir = Path(manifests_dir)
        self._sections: list[Section] | None = None
        self._markdown_cache: dict[str, str] = {}

    def _load_markdown(self, filename: str) -> str:
        """Load and cache markdown content."""
        if filename not in self._markdown_cache:
            filepath = self.rules_dir / filename
            self._markdown_cache[filename] = filepath.read_text(encoding="utf-8")
        return self._markdown_cache[filename]

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

        for manifest_path in sorted(self.manifests_dir.glob("*.json")):
            manifest = self._load_manifest(manifest_path)
            source_file = manifest["file"]
            markdown = self._load_markdown(source_file)

            for section_def in manifest["sections"]:
                content = extract_section_content(markdown, section_def["anchor_heading"])

                if content is None:
                    print(f"Warning: Could not find section '{section_def['id']}' "
                          f"with anchor '{section_def['anchor_heading']}' in {source_file}")
                    continue

                section = Section(
                    id=section_def["id"],
                    title=section_def["title"],
                    description=section_def["description"],
                    keywords=section_def["keywords"],
                    content=content,
                    source_file=source_file,
                    anchor_heading=section_def["anchor_heading"]
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


def main():
    """Demo the section extractor."""
    extractor = SectionExtractor()

    # Load all sections
    sections = extractor.load_all_sections()
    print(f"Loaded {len(sections)} sections from {len(list(extractor.manifests_dir.glob('*.json')))} manifests\n")

    # Show some stats
    by_file = {}
    for section in sections:
        by_file[section.source_file] = by_file.get(section.source_file, 0) + 1

    print("Sections per file:")
    for filename, count in sorted(by_file.items()):
        print(f"  {filename}: {count}")

    # Demo search
    print("\n--- Demo: Searching for 'grapple' ---")
    results = extractor.search_by_text("grapple")
    for section in results[:3]:
        print(f"\n[{section.source_file}] {section.title}")
        print(f"  {section.description}")
        print(f"  Content preview: {section.content[:200]}...")

    # Demo get by ID
    print("\n--- Demo: Get section by ID 'flat_footed_condition' ---")
    section = extractor.get_section_by_id("flat_footed_condition")
    if section:
        print(f"Title: {section.title}")
        print(f"Content:\n{section.content}")


if __name__ == "__main__":
    main()
