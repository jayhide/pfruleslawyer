#!/usr/bin/env python3
"""Preprocess markdown rules files to generate section manifests using Claude."""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from chunking_prompt import format_prompt, format_summarize_prompt, format_class_features_prompt

# Load environment variables from .env file
load_dotenv()

# Mapping of source filenames to descriptive names for context
# These names help the LLM understand what kind of rules each source contains
SOURCE_NAMES = {
    "ability-scores.md": "Ability Scores",
    "afflictions.md": "Afflictions (Curses, Diseases, Poisons)",
    "combat.md": "Combat Rules",
    "conditions.md": "Conditions",
    "creature-types.md": "Creature Types & Subtypes",
    "exploration-movement.md": "Exploration & Movement",
    "glossary.md": "Glossary & Common Terms",
    "magic.md": "Magic Rules",
    "skills.md": "Skills Overview",
    "special-abilities.md": "Special Abilities",
    "universal-monster-rules.md": "Universal Monster Rules",
    "space-reach-threatened-area-templates.md": "Space, Reach and Threatened Area Templates",
    "special-materials.md": "Special Materials",
    "weapons.md": "Weapons",
    "magic-weapons.md": "Magic Weapons",
    "magic-armor.md": "Magic Armor",
    "wondrous-items.md": "Wondrous Items"
}

# Categories that use template-based naming: "Category: Item Name"
# Maps subdirectory name to display category name
CATEGORY_TEMPLATES = {
    "skills": "Skill",
    "spells": "Spell",
    "feats": "Feat",
    "class": "Class"
}

# Description templates by category for template mode (no LLM needed)
# Used when mode="template" in preprocess_config.json
CATEGORY_DESCRIPTION_TEMPLATES = {
    "Spells": "Full description of the spell {title}, including casting time, components, range, and effects.",
    "Feats": "Complete rules for the feat {title}, including prerequisites and benefits.",
    "Archetypes": "Complete description of the {title} archetype, including altered or replaced class features.",
}


def get_source_name(source_path: str) -> str:
    """Get the descriptive source name for a file.

    Args:
        source_path: Path relative to project root (e.g., 'rules/skills/acrobatics.md')

    Returns:
        Descriptive name based on:
        - Category template for subdirectories (e.g., "Skill: Acrobatics")
        - SOURCE_NAMES mapping for top-level files
        - Fallback to title-cased filename
    """
    parts = source_path.replace("\\", "/").split("/")
    filename = parts[-1]

    # Check if file is in a category subdirectory (e.g., rules/skills/acrobatics.md)
    if len(parts) >= 3:
        subdir = parts[-2]  # e.g., "skills"
        if subdir in CATEGORY_TEMPLATES:
            category = CATEGORY_TEMPLATES[subdir]
            item_name = filename.replace(".md", "").replace("-", " ").title()
            return f"{category}: {item_name}"

    # Check top-level SOURCE_NAMES mapping
    if filename in SOURCE_NAMES:
        return SOURCE_NAMES[filename]

    # Fallback: capitalize and remove extension
    return filename.replace(".md", "").replace("-", " ").title()


def extract_json_from_response(text: str) -> dict:
    """Extract JSON from LLM response, handling potential markdown code blocks.

    Args:
        text: The raw response text from the LLM

    Returns:
        Parsed JSON as a dictionary

    Raises:
        ValueError: If no valid JSON found in response
    """
    # Try to find JSON in code blocks first
    code_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if code_block_match:
        return json.loads(code_block_match.group(1))

    # Try to parse the whole response as JSON
    text = text.strip()
    if text.startswith('{'):
        return json.loads(text)

    # Try to find a JSON object anywhere in the text
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(0))

    raise ValueError("No valid JSON found in response")


def process_markdown_full(
    client: anthropic.Anthropic,
    content: str,
    source_path: str,
    model: str = "claude-sonnet-4-20250514",
    timeout: float = 300.0
) -> dict:
    """Process markdown content and generate section manifest (full mode).

    Args:
        client: Anthropic client instance
        content: Markdown content to process
        source_path: Source identifier (e.g., URL or file path)
        model: Claude model to use
        timeout: Request timeout in seconds (default: 300)

    Returns:
        Manifest dictionary with sections

    Raises:
        anthropic.APITimeoutError: If request times out
        anthropic.APIError: If API call fails
        json.JSONDecodeError: If response is not valid JSON
        ValueError: If response is missing required fields
    """
    # Use basename for filename context
    filename = source_path.rstrip("/").split("/")[-1]
    if not filename.endswith(".md"):
        filename = f"{filename}.md"

    # Format the prompt
    prompt = format_prompt(content, filename, source_path)

    # Call Claude API
    message = client.messages.create(
        model=model,
        max_tokens=16384,
        timeout=timeout,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    response_text = message.content[0].text

    # Extract and parse JSON
    manifest = extract_json_from_response(response_text)

    # Validate basic structure
    if "sections" not in manifest:
        raise ValueError("Response missing 'sections' field")

    # Ensure metadata is set correctly
    manifest["file"] = filename
    manifest["source_path"] = source_path
    manifest["source_name"] = get_source_name(source_path)

    return manifest


def process_file(
    client: anthropic.Anthropic,
    file_path: Path,
    output_dir: Path,
    model: str = "claude-sonnet-4-20250514",
    verbose: bool = False,
    timeout: float = 300.0
) -> bool:
    """Process a single markdown file and generate its section manifest.

    Args:
        client: Anthropic client instance
        file_path: Path to the markdown file
        output_dir: Directory to write manifest files
        model: Claude model to use
        verbose: Whether to print detailed progress
        timeout: Request timeout in seconds (default: 300)

    Returns:
        True if successful, False otherwise
    """
    filename = file_path.name
    source_path = f"rules/{filename}"

    if verbose:
        print(f"Processing {filename}...")

    # Read the markdown content
    content = file_path.read_text(encoding="utf-8")

    try:
        manifest = process_markdown_full(client, content, source_path, model, timeout)

        # Write manifest to output file
        output_path = output_dir / f"{file_path.stem}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        if verbose:
            print(f"  -> Generated {len(manifest['sections'])} sections")
            print(f"  -> Saved to {output_path}")

        return True

    except anthropic.APITimeoutError:
        print(f"Timeout processing {filename} (exceeded {timeout}s)", file=sys.stderr)
        return False
    except anthropic.APIError as e:
        print(f"API error processing {filename}: {e}", file=sys.stderr)
        return False
    except json.JSONDecodeError as e:
        print(f"JSON parse error for {filename}: {e}", file=sys.stderr)
        return False
    except ValueError as e:
        print(f"Validation error for {filename}: {e}", file=sys.stderr)
        return False


def extract_title_from_markdown(content: str) -> tuple[str, str]:
    """Extract the H1 title and anchor heading from markdown content.

    Returns:
        Tuple of (title, anchor_heading)
    """
    match = re.search(r'^(# .+)$', content, re.MULTILINE)
    if match:
        anchor_heading = match.group(1)
        title = anchor_heading[2:]  # Remove "# " prefix
        return title, anchor_heading
    return "Unknown", "# Unknown"


def strip_feat_suffix(title: str) -> str:
    """Strip feat type suffix like (Combat), (Achievement) from title.

    Examples:
        "Combat Reflexes (Combat)" -> "Combat Reflexes"
        "Crane Style (Combat, Style)" -> "Crane Style"
        "Chainbreaker (Achievement)" -> "Chainbreaker"
    """
    return re.sub(r'\s*\([^)]+\)\s*$', '', title)


def process_markdown_simple(
    client: anthropic.Anthropic,
    content: str,
    source_path: str,
    model: str = "claude-sonnet-4-20250514",
    timeout: float = 300.0
) -> dict:
    """Process markdown content as a single section (simple mode).

    Args:
        client: Anthropic client instance
        content: Markdown content to process
        source_path: Source identifier (e.g., URL or file path)
        model: Claude model to use
        timeout: Request timeout in seconds (default: 300)

    Returns:
        Manifest dictionary with a single section

    Raises:
        anthropic.APITimeoutError: If request times out
        anthropic.APIError: If API call fails
        json.JSONDecodeError: If response is not valid JSON
    """
    # Use basename for filename context
    filename = source_path.rstrip("/").split("/")[-1]
    if not filename.endswith(".md"):
        filename = f"{filename}.md"

    # Extract title from the markdown
    title, anchor_heading = extract_title_from_markdown(content)

    # Generate section ID from source path
    section_id = filename.replace(".md", "").replace("-", "_")

    # Format the prompt
    prompt = format_summarize_prompt(content, filename)

    # Call Claude API
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        timeout=timeout,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    response_text = message.content[0].text

    # Extract and parse JSON
    result = extract_json_from_response(response_text)

    # Build the manifest in the standard format
    manifest = {
        "file": filename,
        "source_path": source_path,
        "source_name": get_source_name(source_path),
        "sections": [
            {
                "id": section_id,
                "title": title,
                "anchor_heading": anchor_heading,
                "description": result.get("description", ""),
                "keywords": result.get("keywords", [])
            }
        ]
    }

    return manifest


def process_markdown_template(
    content: str,
    source_path: str,
    category: str = "Uncategorized"
) -> dict:
    """Process markdown without LLM - uses template description.

    No API calls required. Uses H1 header as title and
    category-specific description template. Ideal for categories
    like Spells where there are thousands of pages and a template
    description is sufficient.

    Args:
        content: Markdown content to process
        source_path: Source identifier (e.g., URL or file path)
        category: Category name for selecting description template

    Returns:
        Manifest dictionary with a single section
    """
    # Use basename for filename context
    filename = source_path.rstrip("/").split("/")[-1]
    if not filename.endswith(".md"):
        filename = f"{filename}.md"

    # Extract title from the markdown
    title, anchor_heading = extract_title_from_markdown(content)

    # Strip feat type suffix for search (but keep anchor_heading for navigation)
    if category == "Feats":
        title = strip_feat_suffix(title)

    # Generate section ID from source path
    section_id = filename.replace(".md", "").replace("-", "_")

    # Get description template for category
    template = CATEGORY_DESCRIPTION_TEMPLATES.get(
        category,
        "Rules and description for {title}."
    )
    description = template.format(title=title)

    # Build manifest - no keywords needed for template mode
    return {
        "file": filename,
        "source_path": source_path,
        "source_name": get_source_name(source_path),
        "sections": [{
            "id": section_id,
            "title": title,
            "anchor_heading": anchor_heading,
            "description": description,
            "keywords": []
        }]
    }


def slugify(text: str, max_length: int = 60) -> str:
    """Convert text to snake_case slug.

    Args:
        text: Text to convert
        max_length: Maximum length of resulting slug

    Returns:
        Snake_case slug suitable for use as an ID
    """
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)  # Remove punctuation
    text = re.sub(r'\s+', '_', text)     # Spaces to underscores
    text = re.sub(r'_+', '_', text)      # Collapse multiple underscores
    text = text.strip('_')
    return text[:max_length]


def extract_faq_keywords(question: str) -> list[str]:
    """Extract likely keywords from FAQ question text.

    Removes common question words and keeps game-relevant terms.

    Args:
        question: The FAQ question text

    Returns:
        List of keywords (max 10)
    """
    stopwords = {
        'what', 'how', 'does', 'the', 'a', 'an', 'is', 'are', 'if', 'can',
        'when', 'which', 'why', 'who', 'where', 'do', 'this', 'that', 'it',
        'to', 'of', 'in', 'for', 'on', 'with', 'as', 'at', 'by', 'from',
        'or', 'and', 'be', 'have', 'has', 'was', 'were', 'been', 'being',
        'would', 'could', 'should', 'will', 'may', 'might', 'must',
        'my', 'your', 'his', 'her', 'its', 'our', 'their', 'i', 'you', 'he', 'she'
    }
    words = re.findall(r'\b\w+\b', question.lower())
    return [w for w in words if w not in stopwords and len(w) > 2][:10]


def process_markdown_faq(
    markdown: str,
    source_path: str,
    source_name: str = "Paizo FAQ"
) -> dict:
    """Process FAQ markdown into one section per Q&A pair.

    FAQ markdown format (from extract_faq_markdown):
        ## Question text here?

        Answer text here.

        ---

        ## Next question?
        ...

    No LLM call required - pure Python parsing.

    Args:
        markdown: Markdown content with ## questions and answers
        source_path: Source URL or file path
        source_name: Display name for the source

    Returns:
        Manifest dictionary with one section per Q&A pair
    """
    sections = []

    # Split on --- separator or ## headings
    # This handles both "---" separated and consecutive "## " sections
    qa_pairs = re.split(r'\n---\n+|\n(?=## )', markdown)

    for qa in qa_pairs:
        qa = qa.strip()
        if not qa:
            continue

        # Extract question (## heading) and answer
        match = re.match(r'^## (.+?)\n\n(.+)', qa, re.DOTALL)
        if match:
            question, answer = match.groups()
            question = question.strip()
            answer = answer.strip()

            # Generate slugified ID
            slug = slugify(question)
            section_id = f"faq_{slug}"

            # Truncate description if answer is long
            if len(answer) > 150:
                description = answer[:147].strip() + "..."
            else:
                description = answer

            sections.append({
                "id": section_id,
                "title": question,
                "anchor_heading": f"## {question}",
                "description": description,
                "keywords": extract_faq_keywords(question)
            })

    # Use URL path segment as filename
    filename = source_path.rstrip("/").split("/")[-1]
    if not filename.endswith(".md"):
        filename = f"{filename}.md"

    return {
        "file": filename,
        "source_path": source_path,
        "source_name": source_name,
        "sections": sections
    }


def extract_toc_from_markdown(markdown: str) -> str:
    """Extract the Table of Contents block from class markdown.

    The TOC is typically formatted as:
        Contents
        + [Class skills](#class_skills)
        + [Class Features](#class_features)
          - [Spell Combat (Ex)](#spell_combat_ex)
          ...

    Args:
        markdown: Full markdown content

    Returns:
        The TOC block as a string, or empty string if not found
    """
    lines = markdown.split('\n')
    toc_lines = []
    in_toc = False

    for line in lines:
        # Look for TOC start
        if line.strip().lower() == 'contents':
            in_toc = True
            toc_lines.append(line)
            continue

        if in_toc:
            # TOC entries start with +, -, or * followed by [
            if re.match(r'^\s*[-+*]\s+\[', line):
                toc_lines.append(line)
            elif line.strip() == '':
                # Allow blank lines within TOC
                continue
            else:
                # End of TOC
                break

    return '\n'.join(toc_lines)


def extract_class_features(markdown: str, class_name: str) -> list[dict]:
    """Extract individual class features from markdown.

    Identifies H4 headings (####) as class features and extracts their content.

    Args:
        markdown: Full markdown content
        class_name: Name of the class for ID prefixing

    Returns:
        List of feature dicts with 'id', 'title', 'anchor_heading', 'content'
    """
    lines = markdown.split('\n')
    features = []
    current_feature = None
    current_lines = []

    class_prefix = slugify(class_name)

    for i, line in enumerate(lines):
        # Check for H4 heading (class feature)
        match = re.match(r'^(####)\s+(.+)$', line)
        if match:
            # Save previous feature if exists
            if current_feature:
                current_feature['content'] = '\n'.join(current_lines).strip()
                if current_feature['content']:
                    features.append(current_feature)

            heading_text = match.group(2).strip()
            # Strip anchor ID for title
            title_clean, anchor_id = heading_text, None
            anchor_match = re.match(r'^(.+?)\s*\{#([^}]+)\}\s*$', heading_text)
            if anchor_match:
                title_clean = anchor_match.group(1).strip()
                anchor_id = anchor_match.group(2)

            # Generate ID from anchor or title
            if anchor_id:
                feature_id = f"{class_prefix}_{anchor_id}"
            else:
                feature_id = f"{class_prefix}_{slugify(title_clean)}"

            current_feature = {
                'id': feature_id,
                'title': title_clean,
                'anchor_heading': f"#### {heading_text}",
                'content': ''
            }
            current_lines = [line]
        elif current_feature:
            # Check for same or higher level heading (end of feature)
            level = get_heading_level(line)
            if level is not None and level <= 4:
                # Save current feature
                current_feature['content'] = '\n'.join(current_lines).strip()
                if current_feature['content']:
                    features.append(current_feature)
                current_feature = None
                current_lines = []
            else:
                current_lines.append(line)

    # Don't forget the last feature
    if current_feature:
        current_feature['content'] = '\n'.join(current_lines).strip()
        if current_feature['content']:
            features.append(current_feature)

    return features


def get_heading_level(line: str) -> int | None:
    """Get heading level from a markdown line."""
    match = re.match(r'^(#{1,6})\s+', line)
    if match:
        return len(match.group(1))
    return None


def extract_class_overview(markdown: str, class_name: str) -> dict | None:
    """Extract the class overview section (intro through before Class Skills).

    Args:
        markdown: Full markdown content
        class_name: Name of the class

    Returns:
        Feature dict with overview content, or None if not found
    """
    lines = markdown.split('\n')
    start_idx = None
    end_idx = None

    # Find H1 (class title)
    for i, line in enumerate(lines):
        if re.match(r'^#\s+' + re.escape(class_name), line, re.IGNORECASE):
            start_idx = i
            break

    if start_idx is None:
        return None

    # Find first H3 (usually "Class skills" or "Class Features")
    for i in range(start_idx + 1, len(lines)):
        if re.match(r'^###\s+', lines[i]):
            end_idx = i
            break

    if end_idx is None:
        end_idx = len(lines)

    content = '\n'.join(lines[start_idx:end_idx]).strip()
    if not content:
        return None

    class_prefix = slugify(class_name)
    return {
        'id': f"{class_prefix}_overview",
        'title': f"{class_name} (Class Overview)",
        'anchor_heading': f"# {class_name}",
        'end_at_heading': lines[end_idx] if end_idx < len(lines) else None,
        'content': content
    }


def process_markdown_class(
    client: anthropic.Anthropic,
    markdown: str,
    source_path: str,
    source_name: str | None = None,
    model: str = "claude-sonnet-4-20250514",
    timeout: float = 300.0
) -> dict:
    """Process class markdown into feature-based sections.

    Uses predictable class document structure to identify sections,
    then calls Claude to generate descriptions and keywords for each feature.

    Args:
        client: Anthropic client instance
        markdown: Markdown content to process
        source_path: Source identifier (e.g., URL or file path)
        source_name: Optional display name for the source
        model: Claude model to use
        timeout: Request timeout in seconds

    Returns:
        Manifest dictionary with multiple sections (one per feature)
    """
    # Extract class name from markdown
    title, anchor_heading = extract_title_from_markdown(markdown)

    # Generate filename for manifest
    filename = source_path.rstrip("/").split("/")[-1]
    if not filename.endswith(".md"):
        filename = f"{filename}.md"

    # Extract TOC
    toc_content = extract_toc_from_markdown(markdown)

    # Extract overview section
    overview = extract_class_overview(markdown, title)

    # Extract class features (H4 headings)
    features = extract_class_features(markdown, title)

    # Build sections list starting with overview
    sections = []

    if overview:
        sections.append({
            'id': overview['id'],
            'title': overview['title'],
            'anchor_heading': overview['anchor_heading'],
            'end_at_heading': overview.get('end_at_heading'),
            'description': f"Overview of the {title} class including role, alignment, hit die, and starting wealth.",
            'keywords': [title.lower(), 'class', 'hit die', 'role', 'alignment']
        })

    # Call Claude to generate descriptions and keywords for features
    if features:
        prompt = format_class_features_prompt(title, features)

        message = client.messages.create(
            model=model,
            max_tokens=8192,
            timeout=timeout,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text
        result = extract_json_from_response(response_text)
        feature_metadata = result.get('features', {})

        for feature in features:
            metadata = feature_metadata.get(feature['id'], {})
            sections.append({
                'id': feature['id'],
                'title': f"{feature['title']} ({title})",
                'anchor_heading': feature['anchor_heading'],
                'description': metadata.get('description', f"Rules for the {feature['title']} class feature."),
                'keywords': metadata.get('keywords', [feature['title'].lower()])
            })

    # Build manifest
    manifest = {
        'file': filename,
        'source_path': source_path,
        'source_name': source_name or f"Class: {title}",
        'category': 'Classes',
        'toc_content': toc_content,
        'sections': sections
    }

    return manifest


def process_file_simple(
    client: anthropic.Anthropic,
    file_path: Path,
    rules_dir: Path,
    output_dir: Path,
    model: str = "claude-sonnet-4-20250514",
    verbose: bool = False,
    timeout: float = 300.0
) -> bool:
    """Process a single markdown file in simple mode (whole file = one section).

    Args:
        client: Anthropic client instance
        file_path: Path to the markdown file
        rules_dir: Base rules directory (for computing relative paths)
        output_dir: Directory to write manifest files
        model: Claude model to use
        verbose: Whether to print detailed progress
        timeout: Request timeout in seconds (default: 300)

    Returns:
        True if successful, False otherwise
    """
    filename = file_path.name
    # Compute source_path relative to project root (should start with "rules/")
    try:
        relative_path = file_path.relative_to(rules_dir.parent)
        source_path = str(relative_path)
        # Ensure it starts with "rules/"
        if not source_path.startswith("rules/"):
            source_path = f"rules/{source_path}"
    except ValueError:
        source_path = f"rules/{filename}"

    if verbose:
        print(f"Processing {filename} (simple mode)...")

    # Read the markdown content
    content = file_path.read_text(encoding="utf-8")

    try:
        manifest = process_markdown_simple(client, content, source_path, model, timeout)

        # Write manifest to output file
        output_path = output_dir / f"{file_path.stem}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        if verbose:
            print(f"  -> Generated 1 section with {len(manifest['sections'][0].get('keywords', []))} keywords")
            print(f"  -> Saved to {output_path}")

        return True

    except anthropic.APITimeoutError:
        print(f"Timeout processing {filename} (exceeded {timeout}s)", file=sys.stderr)
        return False
    except anthropic.APIError as e:
        print(f"API error processing {filename}: {e}", file=sys.stderr)
        return False
    except json.JSONDecodeError as e:
        print(f"JSON parse error for {filename}: {e}", file=sys.stderr)
        return False
    except ValueError as e:
        print(f"Validation error for {filename}: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Generate section manifests from markdown rules files using Claude"
    )
    parser.add_argument(
        "--rules-dir",
        type=Path,
        default=Path("rules"),
        help="Directory containing markdown rules files (default: rules)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("manifests"),
        help="Directory to write manifest files (default: manifests)"
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-20250514",
        help="Claude model to use (default: claude-sonnet-4-20250514)"
    )
    parser.add_argument(
        "--file",
        type=str,
        help="Process only a specific file (e.g., combat.md)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print detailed progress"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="API request timeout in seconds (default: 300)"
    )
    parser.add_argument(
        "--simple",
        action="store_true",
        help="Simple mode: treat each file as a single section (for pre-split content like skills)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reprocessing of all files, overwriting existing manifests"
    )

    args = parser.parse_args()

    # Validate directories
    if not args.rules_dir.exists():
        print(f"Error: Rules directory '{args.rules_dir}' not found", file=sys.stderr)
        sys.exit(1)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Check for API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable not set", file=sys.stderr)
        print("Set it with: export ANTHROPIC_API_KEY='your-key-here'", file=sys.stderr)
        sys.exit(1)

    # Initialize Anthropic client
    client = anthropic.Anthropic()

    # Find markdown files to process
    if args.file:
        files = [args.rules_dir / args.file]
        if not files[0].exists():
            print(f"Error: File '{files[0]}' not found", file=sys.stderr)
            sys.exit(1)
    else:
        files = sorted(args.rules_dir.glob("*.md"))

    if not files:
        print("No markdown files found to process", file=sys.stderr)
        sys.exit(1)

    mode_str = " (simple mode)" if args.simple else ""

    # Filter out files that already have manifests (unless --force)
    files_to_process = []
    skipped_count = 0
    for file_path in files:
        manifest_path = args.output_dir / f"{file_path.stem}.json"
        if manifest_path.exists() and not args.force:
            skipped_count += 1
            if args.verbose:
                print(f"Skipping {file_path.name} (manifest exists)")
        else:
            files_to_process.append(file_path)

    if skipped_count > 0:
        print(f"Skipping {skipped_count} file(s) with existing manifests (use --force to overwrite)")

    if not files_to_process:
        print("No files to process")
        return

    print(f"Processing {len(files_to_process)} file(s){mode_str}...")

    # Process each file
    success_count = 0
    for file_path in files_to_process:
        if args.simple:
            success = process_file_simple(
                client, file_path, args.rules_dir, args.output_dir,
                args.model, args.verbose, args.timeout
            )
        else:
            success = process_file(
                client, file_path, args.output_dir,
                args.model, args.verbose, args.timeout
            )
        if success:
            success_count += 1

    print(f"\nCompleted: {success_count}/{len(files_to_process)} files processed successfully")

    if success_count < len(files_to_process):
        sys.exit(1)


if __name__ == "__main__":
    main()
