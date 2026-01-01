#!/usr/bin/env python3
"""RAG-powered Pathfinder 1e rules assistant."""

import argparse
import sys

import anthropic
from dotenv import load_dotenv

from vector_store import RulesVectorStore

load_dotenv()

MODEL_IDS = {
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-5-20251101",
}

SYSTEM_PROMPT = """You are a Pathfinder 1st Edition rules expert. Answer the user's question accurately based on the official rules provided in the context below.

Guidelines:
- Base your answer ONLY on the rules provided in the context, and pay close attention to precise wording of definitions and rules
- Specific overrides general: If two rules contradict and one is more specific to the situation at hand, the specific one is correct
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

        source = result.get('source_name', result['source_file'])
        sections.append(f"### {result['title']} (from {source})\n\n{content}")

    return "\n\n---\n\n".join(sections)


def ask_rules_question(
    question: str,
    n_results: int = 7,
    model: str = "sonnet",
    verbose: bool = False,
    rerank: bool = True
) -> str:
    """Ask a question about Pathfinder rules using RAG.

    Args:
        question: The rules question to answer
        n_results: Number of relevant sections to retrieve
        model: Model to use ('sonnet' or 'opus')
        verbose: Whether to print debug info
        rerank: Whether to use cross-encoder reranking

    Returns:
        The answer from Claude
    """
    # Initialize vector store and client
    store = RulesVectorStore()
    client = anthropic.Anthropic()

    # Search for relevant sections
    if verbose:
        print(f"Searching for relevant rules...", file=sys.stderr)

    results = store.query(question, n_results=n_results, rerank=rerank)

    # Always print retrieved sections info
    print(f"Found {len(results)} relevant sections:", file=sys.stderr)
    for r in results:
        source = r.get('source_name', r['source_file'])
        print(f"  - {r['title']} ({source})", file=sys.stderr)

        # Show combined/rerank score if available, otherwise retrieval score
        if 'combined_score' in r:
            print(f"      combined: {r['combined_score']:.3f} (rerank: {r['rerank_score']:.2f}, retrieval: {r['score']:.3f})", file=sys.stderr)
        else:
            print(f"      score: {r['score']:.3f}", file=sys.stderr)

        # Build and show retrieval score breakdown
        components = [f"semantic: {r.get('semantic_score', 0):.3f}"]
        if r.get('keyword_boost', 0) > 0:
            components.append(f"keyword: +{r['keyword_boost']:.2f}")
        if r.get('subheading_boost', 0) > 0:
            components.append(f"subheading: +{r['subheading_boost']:.2f}")
        if r.get('title_boost', 0) > 0:
            components.append(f"title: +{r['title_boost']:.2f}")
        print(f"      retrieval breakdown: {', '.join(components)}", file=sys.stderr)

        # In verbose mode, print the full section content
        if verbose:
            content = r.get("content", "")
            # Strip the metadata header if present
            if "\n\n" in content:
                parts = content.split("\n\n", 1)
                if len(parts) > 1:
                    content = parts[1]
            print(f"\n{content}\n", file=sys.stderr)
            print("---", file=sys.stderr)
    print(file=sys.stderr)

    # Format context and prompt
    context = format_context(results, max_sections=n_results)
    user_prompt = USER_PROMPT_TEMPLATE.format(context=context, question=question)

    if verbose:
        print(f"Context length: {len(context)} chars", file=sys.stderr)
        print(file=sys.stderr)

    # Call Claude
    model_id = MODEL_IDS[model]
    message = client.messages.create(
        model=model_id,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_prompt}
        ]
    )

    return message.content[0].text


def interactive_mode(n_results: int = 5, model: str = "sonnet", rerank: bool = True):
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
            answer = ask_rules_question(question, n_results=n_results, model=model, rerank=rerank)
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
        default=6,
        help="Number of relevant sections to retrieve (default: 6)"
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

    args = parser.parse_args()

    if args.question:
        # Single question mode
        answer = ask_rules_question(
            args.question,
            n_results=args.results,
            model=args.model,
            verbose=args.verbose,
            rerank=not args.no_rerank
        )
        print(answer)
    else:
        # Interactive mode
        interactive_mode(n_results=args.results, model=args.model, rerank=not args.no_rerank)


if __name__ == "__main__":
    main()
