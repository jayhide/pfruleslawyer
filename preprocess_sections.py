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

from chunking_prompt import format_prompt

# Load environment variables from .env file
load_dotenv()


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

        # Ensure file and source_path are set correctly
        manifest["file"] = filename
        manifest["source_path"] = source_path

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

    print(f"Processing {len(files)} file(s)...")

    # Process each file
    success_count = 0
    for file_path in files:
        if process_file(client, file_path, args.output_dir, args.model, args.verbose, args.timeout):
            success_count += 1

    print(f"\nCompleted: {success_count}/{len(files)} files processed successfully")

    if success_count < len(files):
        sys.exit(1)


if __name__ == "__main__":
    main()
