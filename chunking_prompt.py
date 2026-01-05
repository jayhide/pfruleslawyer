"""Prompt template and schema for LLM-powered section extraction from markdown rules files."""

SECTION_SCHEMA = {
    "type": "object",
    "required": ["file", "source_path", "sections"],
    "properties": {
        "file": {"type": "string", "description": "Filename of the markdown file"},
        "source_path": {"type": "string", "description": "Relative path to the source file"},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "title", "anchor_heading", "includes_subheadings", "description", "keywords"],
                "properties": {
                    "id": {"type": "string", "description": "Unique snake_case identifier"},
                    "title": {"type": "string", "description": "Human-readable title"},
                    "anchor_heading": {"type": "string", "description": "Exact markdown heading text including # symbols"},
                    "includes_subheadings": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of subheadings included in this section"
                    },
                    "description": {"type": "string", "description": "Brief description of the rules and terms covered"},
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Keywords for retrieval matching"
                    }
                }
            }
        }
    }
}

CHUNKING_PROMPT = '''You are analyzing a Pathfinder 1e rules document to identify logical sections for a retrieval-augmented generation (RAG) system.

Your task: Identify self-contained "topics" that should be retrieved together when answering rules questions. Each section should contain everything needed to understand that topic.

## Guidelines

1. **Favor LARGER chunks** that keep related rules together. If rules are part of the same general topic, keep them in one section.

2. **Split only when topics are UNRELATED** - when rules would unlikely be relevant to the same query.

3. Each section must be **SELF-CONTAINED** - include all sub-rules, exceptions, and context needed to fully understand the topic.

4. **Anchor headings**: Identify the markdown heading that starts each section (include the # symbols exactly as they appear).

5. **Subheadings**: List all subheadings that fall under this section and should be included when retrieving it.

## Examples of GOOD chunking:

- "Initiative" as one section including: initiative checks, flat-footed at start of combat, tie-breaking rules, inaction
- "Armor Class" as one section including: calculating AC, touch AC, flat-footed AC, all modifier types
- "Grapple" as one section with all grappling rules together
- "Blinded" condition as one section with all mechanical effects
- Summary gives a quick overview of which rules are explained in the section, ie "Mechanics around initiating and escaping grapples"
- Keywords include a small number of specific technical game terms like "initiative", "flat-footed", "grapple"
- Keywords are terms that would indicate this section should be retrieved if they appeared in a user's search, ie "grapple" for the section relevant to "How do I initiate a grapple?"

## Examples of BAD chunking:

- Splitting "Flat-Footed" away from "Initiative" when they're discussing the same combat concept
- Splitting "Attack Roll" from "Automatic Misses and Hits" - these belong together
- Making each small subsection its own chunk when they're all part of one topic
- Keywords include terms that are too broad and generic to be useful for search, or only incidental to the section, like "attack" mentioned in passing in a section about invisibility, or "magic" in a section about transmutation spells, or "humanoid" in a section on orcs
- **Grouping a list of independent definitions into one giant section** - e.g., creature types or subtypes should each be their OWN section, not lumped together

## Important: Lists of Definitions

When a document contains a LIST of independent definitions (creature types, subtypes, conditions, glossary terms, etc.), each definition should be its OWN section. For example:
- Each creature TYPE (Aberration, Animal, Construct, etc.) = separate section
- Each creature SUBTYPE (Air, Aquatic, Cold, Fire, etc.) = separate section
- Each condition (Blinded, Deafened, etc.) = separate section

Do NOT group 20+ subtypes into a single "Subtypes Overview" section - that makes retrieval useless.

## Output Format

Output valid JSON matching this exact structure. Do not include any text before or after the JSON:

{{
  "file": "{filename}",
  "source_path": "{source_path}",
  "sections": [
    {{
      "id": "snake_case_id",
      "title": "Human Readable Title",
      "anchor_heading": "### Exact Heading Text",
      "includes_subheadings": ["#### Subheading 1", "##### Subheading 2"],
      "description": "Brief description of what rules this section covers",
      "keywords": ["keyword1", "keyword2", "keyword3"]
    }}
  ]
}}

## Document to Analyze

Filename: {filename}

<document>
{markdown_content}
</document>'''


def format_prompt(markdown_content: str, filename: str, source_path: str) -> str:
    """Format the chunking prompt with the given markdown content.

    Args:
        markdown_content: The full text of the markdown file
        filename: The name of the file (e.g., "combat.md")
        source_path: Relative path to the file (e.g., "rules/combat.md")

    Returns:
        The formatted prompt ready to send to the LLM
    """
    return CHUNKING_PROMPT.format(
        markdown_content=markdown_content,
        filename=filename,
        source_path=source_path
    )


SUMMARIZE_PROMPT = '''You are analyzing a Pathfinder 1e rules document to generate metadata for a retrieval-augmented generation (RAG) system.

This document should be treated as a SINGLE section (do not split it). Your task is to generate a description and keywords that will help this document be retrieved when relevant.

## Guidelines

1. **Description**: Write a brief (1-2 sentence) summary of what rules this document covers. Focus on the mechanical aspects that players/GMs would search for.

2. **Keywords**: List the set of specific game terms that should trigger retrieval of this document. Include:
   - The main topic name and common variations
   - Specific uses or applications mentioned

Do not use generic or general terms as keywords, stick to terms that should trigger retrieval of these rules.

3. **Subheadings**: List ALL markdown headings (###, ####, etc.) found in the document.

## Output Format

Output valid JSON matching this exact structure. Do not include any text before or after the JSON:

{{
  "description": "Brief description of the rules covered",
  "keywords": ["keyword1", "keyword2", "keyword3"],
  "subheadings": ["### Heading 1", "#### Heading 2"]
}}

## Document to Analyze

Filename: {filename}

<document>
{markdown_content}
</document>'''


def format_summarize_prompt(markdown_content: str, filename: str) -> str:
    """Format the summarize prompt for whole-file processing.

    Args:
        markdown_content: The full text of the markdown file
        filename: The name of the file (e.g., "acrobatics.md")

    Returns:
        The formatted prompt ready to send to the LLM
    """
    return SUMMARIZE_PROMPT.format(
        markdown_content=markdown_content,
        filename=filename
    )
