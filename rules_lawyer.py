#!/usr/bin/env python3
"""RAG-powered Pathfinder 1e rules assistant."""

import argparse
import sys

import anthropic

# ANSI color codes for output
class Colors:
    CYAN = "\033[36m"      # Search queries, context headers
    YELLOW = "\033[33m"    # Section titles
    DIM = "\033[2m"        # Scores, debug info
    MAGENTA = "\033[35m"   # Model reasoning
    RED = "\033[31m"       # Warnings
    GREEN = "\033[32m"     # Success messages
    RESET = "\033[0m"      # Reset to default
from dotenv import load_dotenv

from vector_store import RulesVectorStore

load_dotenv()

MODEL_IDS = {
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-5-20251101",
}

SEARCH_TOOL = {
    "name": "search_rules",
    "description": "Search the Pathfinder 1e rules database for additional rules sections. Use this when you need more information about specific rules, conditions, abilities, or mechanics not covered in the provided context. It's best to use this to look up one specific term or mechanic at a time.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query - be specific about what rule or mechanic you're looking for"
            }
        },
        "required": ["query"]
    }
}

FOLLOW_LINK_TOOL = {
    "name": "follow_link",
    "description": "Follow a link to retrieve the rules content at that URL. Use this when you see a link in the rules text that you want to read. Supports URLs with fragments (e.g., #TOC-Grapple) to jump to specific sections.",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to follow (can include #fragment to jump to a specific section)"
            }
        },
        "required": ["url"]
    }
}

SYSTEM_PROMPT = """You are a Pathfinder 1st Edition rules expert. You will be provided with relevant rules context to answer questions.

You have two tools available:
- search_rules: Search for rules by topic when you need information not in the provided context
- follow_link: Follow a URL link in the rules text to read the linked content

Guidelines:
- Base your answer on the rules provided and any additional rules you retrieve
- Pay close attention to specific wording and constraints
- If a rule references another rule without definition, use search_rules or follow_link to look it up
  - Example: If the shape change ability says it works "as with polymorph", search for "polymorph"
  - Example: If you see a link like [grappled](https://...), use follow_link to read it
- Rules are cumulative. If one rule references another, both definitions apply unless stated otherwise
- If the context doesn't contain enough information to fully answer, say so
- Cite specific rules when possible (e.g., "According to the Grappled condition...")
- Be concise but thorough
- If rules interact in complex ways, explain the interaction clearly"""

USER_PROMPT_TEMPLATE = """## Initial Rules Search Results

{context}

## Question

{question}

Please answer the question based on these rules or search for more rules if needed. Reason step-by-step to yourself before you give your final answer."""


def format_context(results: list[dict], max_sections: int = 5) -> str:
    """Format search results as context for the prompt.

    Args:
        results: List of search results from vector store
        max_sections: Maximum number of sections to include

    Returns:
        Formatted context string
    """
    sections = []
    for i, result in enumerate(results[:max_sections], 1):
        # Extract just the content part (after the metadata header)
        content = result.get("content", "")
        # The content includes Title/Description/Keywords header, extract just the rules
        if "\n\n" in content:
            # Skip the metadata header we added during indexing
            parts = content.split("\n\n", 1)
            if len(parts) > 1:
                content = parts[1]

        source = result.get('source_name', result['source_file'])
        sections.append(f"### {result['title']} (from {source})\n\n{content}")

    return "\n\n---\n\n".join(sections)


def print_search_results(results: list[dict], verbose: bool = False) -> None:
    """Print search results to stderr for debugging."""
    print(f"  {Colors.DIM}Found {len(results)} sections:{Colors.RESET}", file=sys.stderr)
    for r in results:
        source = r.get('source_name', r['source_file'])
        print(f"    {Colors.YELLOW}- {r['title']}{Colors.RESET} {Colors.DIM}({source}){Colors.RESET}", file=sys.stderr)
        if verbose:
            # Show score breakdown
            if 'combined_score' in r:
                print(f"        {Colors.DIM}combined: {r['combined_score']:.3f}{Colors.RESET}", file=sys.stderr)
            else:
                print(f"        {Colors.DIM}score: {r['score']:.3f}{Colors.RESET}", file=sys.stderr)

            # Show content
            content = r.get("content", "")
            # Strip the metadata header if present
            if "\n\n" in content:
                parts = content.split("\n\n", 1)
                if len(parts) > 1:
                    content = parts[1]
            print(f"\n{Colors.DIM}{content}{Colors.RESET}\n", file=sys.stderr)
            print(f"{Colors.DIM}---{Colors.RESET}", file=sys.stderr)


def execute_search(query: str, store: RulesVectorStore, n_results: int = 5,
                   rerank: bool = True, verbose: bool = False) -> str:
    """Execute a search and return formatted results for tool response."""
    results = store.query(query, n_results=n_results, rerank=rerank)
    print_search_results(results, verbose)
    return format_context(results, max_sections=n_results)


def ask_rules_question(
    question: str,
    n_results: int = 7,
    model: str = "sonnet",
    verbose: bool = False,
    rerank: bool = True,
    use_tools: bool = True
) -> str:
    """Ask a question about Pathfinder rules using RAG.

    Args:
        question: The rules question to answer
        n_results: Number of relevant sections to retrieve
        model: Model to use ('sonnet' or 'opus')
        verbose: Whether to print debug info
        rerank: Whether to use cross-encoder reranking
        use_tools: Whether to allow model to issue additional searches

    Returns:
        The answer from Claude
    """
    # Initialize vector store and client
    store = RulesVectorStore()
    client = anthropic.Anthropic()

    # Initial search for relevant sections
    print(f"{Colors.CYAN}[Initial search]{Colors.RESET} \"{question}\"", file=sys.stderr)
    results = store.query(question, n_results=n_results, rerank=rerank)

    # Print retrieved sections info
    print(f"{Colors.CYAN}Found {len(results)} relevant sections:{Colors.RESET}", file=sys.stderr)
    for r in results:
        source = r.get('source_name', r['source_file'])
        print(f"  {Colors.YELLOW}- {r['title']}{Colors.RESET} {Colors.DIM}({source}){Colors.RESET}", file=sys.stderr)

        # Show combined/rerank score if available, otherwise retrieval score
        if 'combined_score' in r:
            print(f"      {Colors.DIM}combined: {r['combined_score']:.3f} (rerank: {r['rerank_score']:.2f}, retrieval: {r['score']:.3f}){Colors.RESET}", file=sys.stderr)
        else:
            print(f"      {Colors.DIM}score: {r['score']:.3f}{Colors.RESET}", file=sys.stderr)

        # Build and show retrieval score breakdown
        components = [f"semantic: {r.get('semantic_score', 0):.3f}"]
        if r.get('keyword_boost', 0) > 0:
            components.append(f"keyword: +{r['keyword_boost']:.2f}")
        if r.get('subheading_boost', 0) > 0:
            components.append(f"subheading: +{r['subheading_boost']:.2f}")
        if r.get('title_boost', 0) > 0:
            components.append(f"title: +{r['title_boost']:.2f}")
        print(f"      {Colors.DIM}retrieval breakdown: {', '.join(components)}{Colors.RESET}", file=sys.stderr)

        # In verbose mode, print the full section content
        if verbose:
            content = r.get("content", "")
            # Strip the metadata header if present
            if "\n\n" in content:
                parts = content.split("\n\n", 1)
                if len(parts) > 1:
                    content = parts[1]
            print(f"\n{Colors.DIM}{content}{Colors.RESET}\n", file=sys.stderr)
            print(f"{Colors.DIM}---{Colors.RESET}", file=sys.stderr)
    print(file=sys.stderr)

    # Format context and prompt
    context = format_context(results, max_sections=n_results)
    user_prompt = USER_PROMPT_TEMPLATE.format(context=context, question=question)

    if verbose:
        print(f"Context length: {len(context)} chars", file=sys.stderr)
        print(file=sys.stderr)

    # Build messages for the conversation
    messages = [{"role": "user", "content": user_prompt}]
    model_id = MODEL_IDS[model]

    # Agentic loop - allow model to issue additional searches
    max_tool_calls = 5
    tool_calls = 0

    while True:
        # Call Claude (with or without tools)
        kwargs = {
            "model": model_id,
            "max_tokens": 2048,
            "system": SYSTEM_PROMPT,
            "messages": messages,
        }
        if use_tools:
            kwargs["tools"] = [SEARCH_TOOL, FOLLOW_LINK_TOOL]

        response = client.messages.create(**kwargs)

        # Process response content blocks
        text_response = ""
        tool_uses = []

        for block in response.content:
            if block.type == "text":
                text_response += block.text
                # In verbose mode, show reasoning if there are also tool calls
                if verbose and response.stop_reason == "tool_use":
                    print(f"{Colors.MAGENTA}[Reasoning] {block.text}{Colors.RESET}", file=sys.stderr)
            elif block.type == "tool_use":
                tool_uses.append(block)

        # If no tool use, we're done
        if response.stop_reason != "tool_use" or not tool_uses:
            return text_response

        # Check tool call limit
        if tool_calls >= max_tool_calls:
            print(f"{Colors.RED}[Warning] Reached max tool calls ({max_tool_calls}), returning current response{Colors.RESET}", file=sys.stderr)
            return text_response if text_response else "I was unable to complete the search. Please try rephrasing your question."

        # Process tool calls
        tool_results = []
        for tool_use in tool_uses:
            if tool_use.name == "search_rules":
                query = tool_use.input.get("query", "")
                tool_calls += 1
                print(f"{Colors.CYAN}[Search {tool_calls}]{Colors.RESET} \"{query}\"", file=sys.stderr)

                # Execute the search
                search_results = execute_search(
                    query, store, n_results=n_results,
                    rerank=rerank, verbose=verbose
                )

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": search_results
                })

            elif tool_use.name == "follow_link":
                url = tool_use.input.get("url", "")
                tool_calls += 1
                print(f"{Colors.CYAN}[Follow link {tool_calls}]{Colors.RESET} {url}", file=sys.stderr)

                # Resolve the link
                result = store.resolve_link(url)

                if "error" in result:
                    print(f"  {Colors.RED}Error: {result['error']}{Colors.RESET}", file=sys.stderr)
                    content = f"Error: {result['error']}"
                    if "available_sections" in result:
                        content += f"\nAvailable sections: {', '.join(result['available_sections'])}"
                else:
                    print(f"  {Colors.YELLOW}-> {result['title']}{Colors.RESET} {Colors.DIM}({result['source_name']}){Colors.RESET}", file=sys.stderr)
                    # Format similar to search results
                    content = f"### {result['title']} (from {result['source_name']})\n\n{result['content']}"

                    # In verbose mode, print the content
                    if verbose:
                        print(f"\n{Colors.DIM}{result['content']}{Colors.RESET}\n", file=sys.stderr)
                        print(f"{Colors.DIM}---{Colors.RESET}", file=sys.stderr)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": content
                })

        # Add assistant response and tool results to messages
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})


def interactive_mode(n_results: int = 5, model: str = "sonnet", rerank: bool = True, use_tools: bool = True):
    """Run in interactive mode, answering questions until user quits."""
    print("Pathfinder 1e Rules Lawyer")
    if use_tools:
        print("(Model can issue additional searches as needed)")
    print("Ask any rules question. Type 'quit' or 'exit' to stop.\n")

    while True:
        try:
            question = input("Question: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not question:
            continue

        if question.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        try:
            answer = ask_rules_question(
                question, n_results=n_results, model=model,
                rerank=rerank, use_tools=use_tools
            )
            print(f"\n{answer}\n")
        except Exception as e:
            print(f"{Colors.RED}Error: {e}{Colors.RESET}\n", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Ask questions about Pathfinder 1e rules using RAG"
    )
    parser.add_argument(
        "question",
        nargs="?",
        help="The rules question to ask (omit for interactive mode)"
    )
    parser.add_argument(
        "-n", "--results",
        type=int,
        default=3,
        help="Number of relevant sections to retrieve (default: 3)"
    )
    parser.add_argument(
        "--model",
        choices=["sonnet", "opus"],
        default="sonnet",
        help="Claude model to use: sonnet or opus (default: sonnet)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print debug information"
    )
    parser.add_argument(
        "--no-rerank",
        action="store_true",
        help="Disable cross-encoder reranking"
    )
    parser.add_argument(
        "--no-tools",
        action="store_true",
        help="Disable model-initiated searches (use only initial context)"
    )

    args = parser.parse_args()

    if args.question:
        # Single question mode
        answer = ask_rules_question(
            args.question,
            n_results=args.results,
            model=args.model,
            verbose=args.verbose,
            rerank=not args.no_rerank,
            use_tools=not args.no_tools
        )
        print(answer)
    else:
        # Interactive mode
        interactive_mode(
            n_results=args.results,
            model=args.model,
            rerank=not args.no_rerank,
            use_tools=not args.no_tools
        )


if __name__ == "__main__":
    main()
