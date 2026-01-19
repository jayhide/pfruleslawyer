"""RAG module for rules question answering."""

from .rules_lawyer import (
    Colors,
    MODEL_IDS,
    SEARCH_TOOL,
    FOLLOW_LINK_TOOL,
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
    format_context,
    format_score_breakdown,
    print_search_results,
    execute_search,
    ask_rules_question,
    interactive_mode,
)

__all__ = [
    "Colors",
    "MODEL_IDS",
    "SEARCH_TOOL",
    "FOLLOW_LINK_TOOL",
    "SYSTEM_PROMPT",
    "USER_PROMPT_TEMPLATE",
    "format_context",
    "format_score_breakdown",
    "print_search_results",
    "execute_search",
    "ask_rules_question",
    "interactive_mode",
]
