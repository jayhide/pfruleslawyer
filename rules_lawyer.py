#!/usr/bin/env python3
"""RAG-powered Pathfinder 1e rules assistant."""

import argparse
import sys

import anthropic
from dotenv import load_dotenv

from vector_store import RulesVectorStore

load_dotenv()

SYSTEM_PROMPT = """You are a Pathfinder 1st Edition rules expert. Answer the user's question accurately based on the official rules provided in the context below.

Guidelines:
- Base your answer ONLY on the rules provided in the context
- If the context doesn't contain enough information to fully answer, say so
- Cite specific rules when possible (e.g., "According to the Grappled condition...")
- Be concise but thorough
- If rules interact in complex ways, explain the interaction clearly
- Use game terminology accurately"""

USER_PROMPT_TEMPLATE = """## Relevant Rules

{context}

## Question

{question}

Please answer based on the rules provided above."""


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

        sections.append(f"### {result['title']} (from {result['source_file']})\n\n{content}")

    return "\n\n---\n\n".join(sections)


def ask_rules_question(
    question: str,
    n_results: int = 7,
    model: str = "claude-sonnet-4-20250514",
    verbose: bool = False
) -> str:
    """Ask a question about Pathfinder rules using RAG.

    Args:
        question: The rules question to answer
        n_results: Number of relevant sections to retrieve
        model: Claude model to use
        verbose: Whether to print debug info

    Returns:
        The answer from Claude
    """
    # Initialize vector store and client
    store = RulesVectorStore()
    client = anthropic.Anthropic()

    # Search for relevant sections
    if verbose:
        print(f"Searching for relevant rules...", file=sys.stderr)

    results = store.query(question, n_results=n_results)

    if verbose:
        print(f"Found {len(results)} relevant sections:", file=sys.stderr)
        for r in results:
            # Build retrieval score breakdown
            components = [f"semantic: {r.get('semantic_score', 0):.3f}"]
            if r.get('keyword_boost', 0) > 0:
                components.append(f"keyword: +{r['keyword_boost']:.2f}")
            if r.get('subheading_boost', 0) > 0:
                components.append(f"subheading: +{r['subheading_boost']:.2f}")
            if r.get('title_boost', 0) > 0:
                components.append(f"title: +{r['title_boost']:.2f}")
            retrieval_breakdown = ", ".join(components)

            # Show combined/rerank score if available
            if 'combined_score' in r:
                print(f"  - {r['title']}", file=sys.stderr)
                print(f"      combined: {r['combined_score']:.3f} (rerank: {r['rerank_score']:.2f}, retrieval: {r['score']:.3f})", file=sys.stderr)
            else:
                print(f"  - {r['title']} (score: {r['score']:.3f} | {retrieval_breakdown})", file=sys.stderr)
        print(file=sys.stderr)

    # Format context and prompt
    context = format_context(results, max_sections=n_results)
    user_prompt = USER_PROMPT_TEMPLATE.format(context=context, question=question)

    if verbose:
        print(f"Context length: {len(context)} chars", file=sys.stderr)
        print(file=sys.stderr)

    # Call Claude
    message = client.messages.create(
        model=model,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_prompt}
        ]
    )

    return message.content[0].text


def interactive_mode(n_results: int = 5, model: str = "claude-sonnet-4-20250514"):
    """Run in interactive mode, answering questions until user quits."""
    print("Pathfinder 1e Rules Lawyer")
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
            answer = ask_rules_question(question, n_results=n_results, model=model)
            print(f"\n{answer}\n")
        except Exception as e:
            print(f"Error: {e}\n", file=sys.stderr)


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
        default=7,
        help="Number of relevant sections to retrieve (default: 7)"
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-20250514",
        help="Claude model to use"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print debug information"
    )

    args = parser.parse_args()

    if args.question:
        # Single question mode
        answer = ask_rules_question(
            args.question,
            n_results=args.results,
            model=args.model,
            verbose=args.verbose
        )
        print(answer)
    else:
        # Interactive mode
        interactive_mode(n_results=args.results, model=args.model)


if __name__ == "__main__":
    main()
