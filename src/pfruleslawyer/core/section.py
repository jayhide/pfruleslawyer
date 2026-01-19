"""Section dataclass for rules content."""

from dataclasses import dataclass


@dataclass
class Section:
    """A section of rules content extracted from markdown."""
    id: str
    title: str
    description: str
    keywords: list[str]
    content: str
    source_file: str
    source_name: str
    anchor_heading: str
    category: str = "Uncategorized"

    def __repr__(self) -> str:
        content_preview = self.content[:100] + "..." if len(self.content) > 100 else self.content
        return f"Section(id={self.id!r}, title={self.title!r}, content={content_preview!r})"
