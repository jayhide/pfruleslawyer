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

from chunking_prompt import format_prompt, format_summarize_prompt

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

    # Format the prompt
    prompt = format_prompt(content, filename, source_path)

    try:
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

        # Ensure file, source_path, and source_name are set correctly
        manifest["file"] = filename
        manifest["source_path"] = source_path
        manifest["source_name"] = get_source_name(source_path)

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
        if verbose:
            print(f"  Response was: {response_text[:500]}...", file=sys.stderr)
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

    # Extract title from the markdown
    title, anchor_heading = extract_title_from_markdown(content)

    # Generate section ID from filename
    section_id = file_path.stem.replace("-", "_")

    # Format the prompt
    prompt = format_summarize_prompt(content, filename)

    try:
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
                    "includes_subheadings": result.get("subheadings", []),
                    "description": result.get("description", ""),
                    "keywords": result.get("keywords", [])
                }
            ]
        }

        # Write manifest to output file
        output_path = output_dir / f"{file_path.stem}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        if verbose:
            print(f"  -> Generated 1 section with {len(result.get('keywords', []))} keywords")
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
        if verbose:
            print(f"  Response was: {response_text[:500]}...", file=sys.stderr)
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
