"""Individual markdown modification operations."""

import re


def remove_section(
    markdown: str,
    start_heading: str,
    end_heading: str | None = None
) -> tuple[str, str | None]:
    """Remove a section from markdown content.

    Removes all content from start_heading until:
    - end_heading if specified, OR
    - The next heading at the same or higher level (fewer # symbols)

    Args:
        markdown: The markdown content to modify
        start_heading: Heading text to start removal (e.g., "## Third-Party Options")
        end_heading: Optional heading text to stop at (not removed)

    Returns:
        Tuple of (modified_markdown, change_description or None if no change)
    """
    lines = markdown.split('\n')

    # Parse start heading level
    start_match = re.match(r'^(#{1,6})\s+(.+)$', start_heading)
    if not start_match:
        return markdown, None

    start_level = len(start_match.group(1))
    start_text = start_match.group(2).strip()

    # Parse end heading if provided
    end_level = None
    end_text = None
    if end_heading:
        end_match = re.match(r'^(#{1,6})\s+(.+)$', end_heading)
        if end_match:
            end_level = len(end_match.group(1))
            end_text = end_match.group(2).strip()

    # Find the start line
    start_idx = None
    for i, line in enumerate(lines):
        heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2).strip()
            # Strip anchor IDs like {#id}
            text = re.sub(r'\s*\{#[^}]+\}\s*$', '', text)
            if level == start_level and text == start_text:
                start_idx = i
                break

    if start_idx is None:
        return markdown, None

    # Find the end line
    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        heading_match = re.match(r'^(#{1,6})\s+(.+)$', lines[i])
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2).strip()
            text = re.sub(r'\s*\{#[^}]+\}\s*$', '', text)

            # Check for end_heading match
            if end_text and text == end_text:
                if end_level is None or level == end_level:
                    end_idx = i
                    break

            # Check for same or higher level heading (stops the section)
            if level <= start_level:
                end_idx = i
                break

    # Remove the section
    removed_lines = end_idx - start_idx
    result_lines = lines[:start_idx] + lines[end_idx:]
    result = '\n'.join(result_lines)

    change_desc = f"Removed section '{start_heading}' ({removed_lines} lines)"
    return result, change_desc


def remove_lines(markdown: str, pattern: str) -> tuple[str, str | None]:
    """Remove lines matching a regex pattern.

    Args:
        markdown: The markdown content to modify
        pattern: Regex pattern to match lines

    Returns:
        Tuple of (modified_markdown, change_description or None if no change)
    """
    regex = re.compile(pattern)
    lines = markdown.split('\n')
    original_count = len(lines)

    filtered_lines = [line for line in lines if not regex.search(line)]

    removed_count = original_count - len(filtered_lines)
    if removed_count == 0:
        return markdown, None

    result = '\n'.join(filtered_lines)
    change_desc = f"Removed {removed_count} lines matching pattern '{pattern}'"
    return result, change_desc


def remove_text(markdown: str, text: str) -> tuple[str, str | None]:
    """Remove exact text occurrences.

    Args:
        markdown: The markdown content to modify
        text: Exact text to remove

    Returns:
        Tuple of (modified_markdown, change_description or None if no change)
    """
    if text not in markdown:
        return markdown, None

    count = markdown.count(text)
    result = markdown.replace(text, '')
    change_desc = f"Removed {count} occurrence(s) of text ({len(text)} chars each)"
    return result, change_desc


def replace_text(
    markdown: str,
    pattern: str,
    replacement: str
) -> tuple[str, str | None]:
    """Replace text matching a regex pattern.

    Args:
        markdown: The markdown content to modify
        pattern: Regex pattern to match
        replacement: Replacement text (can use backreferences like \\1)

    Returns:
        Tuple of (modified_markdown, change_description or None if no change)
    """
    regex = re.compile(pattern, re.DOTALL)

    # Count matches first
    matches = regex.findall(markdown)
    if not matches:
        return markdown, None

    result = regex.sub(replacement, markdown)
    change_desc = f"Replaced {len(matches)} match(es) of pattern '{pattern}'"
    return result, change_desc


# Map operation type names to functions
OPERATIONS = {
    "remove_section": remove_section,
    "remove_lines": remove_lines,
    "remove_text": remove_text,
    "replace": replace_text,
}


def apply_operation(markdown: str, operation: dict) -> tuple[str, str | None]:
    """Apply a single operation to markdown content.

    Args:
        markdown: The markdown content to modify
        operation: Operation dict with 'type' and type-specific parameters

    Returns:
        Tuple of (modified_markdown, change_description or None if no change)

    Raises:
        ValueError: If operation type is unknown or missing required params
    """
    op_type = operation.get("type")
    if not op_type:
        raise ValueError("Operation missing 'type' field")

    if op_type not in OPERATIONS:
        raise ValueError(f"Unknown operation type: {op_type}")

    if op_type == "remove_section":
        start_heading = operation.get("start_heading")
        if not start_heading:
            raise ValueError("remove_section requires 'start_heading'")
        end_heading = operation.get("end_heading")
        return remove_section(markdown, start_heading, end_heading)

    elif op_type == "remove_lines":
        pattern = operation.get("pattern")
        if not pattern:
            raise ValueError("remove_lines requires 'pattern'")
        return remove_lines(markdown, pattern)

    elif op_type == "remove_text":
        text = operation.get("text")
        if not text:
            raise ValueError("remove_text requires 'text'")
        return remove_text(markdown, text)

    elif op_type == "replace":
        pattern = operation.get("pattern")
        replacement = operation.get("replacement")
        if not pattern:
            raise ValueError("replace requires 'pattern'")
        if replacement is None:
            raise ValueError("replace requires 'replacement'")
        return replace_text(markdown, pattern, replacement)

    # Should never reach here due to earlier check
    raise ValueError(f"Unhandled operation type: {op_type}")
