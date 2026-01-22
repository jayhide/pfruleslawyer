# RAG Module

Retrieval-Augmented Generation for answering rules questions.

## Files

- `rules_lawyer.py` - Core Q&A logic with tool use

## Key Functions

### ask_rules_question()
Main entry point for asking rules questions.

```python
answer = ask_rules_question(
    "How does grappling work?",
    n_results=7,      # Sections to retrieve
    model="sonnet",   # or "opus"
    verbose=False,    # Print debug info
    rerank=True,      # Use cross-encoder
    use_tools=True,   # Allow follow-up searches
    timing=False      # Show timing breakdown
)
```

### interactive_mode()
REPL for continuous Q&A sessions.

## Tools

The model has access to two tools:
- `search_rules` - Search for additional rules sections
- `follow_link` - Follow URLs in rules text (supports fragments)

## Flow

1. Initial vector search for relevant sections
2. Format context and send to Claude
3. Model can issue tool calls for more information
4. Loop until model responds without tool use (max 5 calls)
