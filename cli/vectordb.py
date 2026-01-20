#!/usr/bin/env python3
"""CLI for managing the rules vector store."""

import argparse

from pfruleslawyer.search import RulesVectorStore
from pfruleslawyer.search.vector_store import build_index


def main():
    """Build index and run queries."""
    parser = argparse.ArgumentParser(description="Build and query the rules vector store")
    parser.add_argument("--build", action="store_true", help="Build/rebuild the index")
    parser.add_argument("--query", "-q", type=str, help="Query to search for")
    parser.add_argument("--results", "-n", type=int, default=5, help="Number of results")
    parser.add_argument("--no-rerank", action="store_true", help="Disable cross-encoder reranking")
    parser.add_argument(
        "--reranker",
        choices=["ms-marco", "bge-large"],
        default="ms-marco",
        help="Cross-encoder model for reranking (default: ms-marco)"
    )

    args = parser.parse_args()

    if args.build:
        build_index()
        print()

    if args.query:
        store = RulesVectorStore()
        rerank = not args.no_rerank
        results = store.query(args.query, n_results=args.results, rerank=rerank, reranker_model=args.reranker)

        print(f"Query: {args.query}")
        print(f"Found {len(results)} results (rerank={'on' if rerank else 'off'}):\n")

        for i, result in enumerate(results, 1):
            print(f"{i}. [{result['source_file']}] {result['title']}")

            # Show combined/rerank score if available, otherwise retrieval score
            if 'combined_score' in result:
                print(f"   Combined score: {result['combined_score']:.3f} (rerank: {result['rerank_score']:.2f}, retrieval: {result['score']:.3f})")
            else:
                print(f"   Score: {result['score']:.3f}")

            # Build retrieval score breakdown
            components = [f"semantic: {result.get('semantic_score', 0):.3f}"]
            if result.get('keyword_boost', 0) > 0:
                components.append(f"keyword: +{result['keyword_boost']:.2f}")
            if result.get('subheading_boost', 0) > 0:
                components.append(f"subheading: +{result['subheading_boost']:.2f}")
            if result.get('title_boost', 0) > 0:
                components.append(f"title: +{result['title_boost']:.2f}")
            print(f"   Retrieval breakdown: {', '.join(components)}")

            print(f"   {result['description']}")
            print()

    if not args.build and not args.query:
        # Default: show stats or build if needed
        store = RulesVectorStore()
        stats = store.get_stats()

        if stats["document_count"] == 0:
            print("No index found. Building index...")
            build_index()
        else:
            print("Vector store stats:")
            for key, value in stats.items():
                print(f"  {key}: {value}")

            print("\nExample queries:")
            print('  poetry run python -m cli.vectordb -q "how does grappling work"')
            print('  poetry run python -m cli.vectordb -q "attack of opportunity"')
            print('  poetry run python -m cli.vectordb -q "what happens when I fall unconscious"')


if __name__ == "__main__":
    main()
