"""LLM-powered preprocessing for section extraction."""

from .prompts import (
    SECTION_SCHEMA,
    CHUNKING_PROMPT,
    SUMMARIZE_PROMPT,
    CLASS_FEATURES_PROMPT,
    format_prompt,
    format_summarize_prompt,
    format_class_features_prompt,
)
from .processor import (
    get_source_name,
    extract_json_from_response,
    process_markdown_full,
    process_markdown_simple,
    process_markdown_template,
    process_markdown_faq,
    process_markdown_class,
    process_file,
    process_file_simple,
)
from .from_db import (
    load_config,
    url_to_manifest_filename,
    resolve_urls_for_entry,
    process_url,
    get_urls_to_process,
)

__all__ = [
    # Prompts
    "SECTION_SCHEMA",
    "CHUNKING_PROMPT",
    "SUMMARIZE_PROMPT",
    "CLASS_FEATURES_PROMPT",
    "format_prompt",
    "format_summarize_prompt",
    "format_class_features_prompt",
    # Processor
    "get_source_name",
    "extract_json_from_response",
    "process_markdown_full",
    "process_markdown_simple",
    "process_markdown_template",
    "process_markdown_faq",
    "process_markdown_class",
    "process_file",
    "process_file_simple",
    # From DB
    "load_config",
    "url_to_manifest_filename",
    "resolve_urls_for_entry",
    "process_url",
    "get_urls_to_process",
]
