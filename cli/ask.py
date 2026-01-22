#!/usr/bin/env python3
"""CLI for asking Pathfinder 1e rules questions using RAG."""

import argparse
import sys

from pfruleslawyer.rag import ask_rules_question, interactive_mode, Colors


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
        "--reranker",
        choices=["ms-marco", "bge-large"],
        default="ms-marco",
        help="Cross-encoder model for reranking (default: ms-marco)"
    )
    parser.add_argument(
        "--no-tools",
        action="store_true",
        help="Disable model-initiated searches (use only initial context)"
    )
    parser.add_argument(
        "--timing",
        action="store_true",
        help="Show timing breakdown for each operation"
    )

    args = parser.parse_args()

    try:
        if args.question:
            # Single question mode
            answer = ask_rules_question(
                args.question,
                n_results=args.results,
                model=args.model,
                verbose=args.verbose,
                rerank=not args.no_rerank,
                use_tools=not args.no_tools,
                reranker_model=args.reranker,
                timing=args.timing
            )
            print(answer)
        else:
            # Interactive mode
            interactive_mode(
                n_results=args.results,
                model=args.model,
                rerank=not args.no_rerank,
                use_tools=not args.no_tools,
                verbose=args.verbose,
                reranker_model=args.reranker,
                timing=args.timing
            )
    except KeyboardInterrupt:
        print(f"\n{Colors.DIM}Interrupted{Colors.RESET}", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
