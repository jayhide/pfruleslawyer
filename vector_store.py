"""Vector store for semantic search over rules sections using ChromaDB."""

import json
import re
import chromadb
from chromadb.utils import embedding_functions
from pathlib import Path

from section_extractor import Section, SectionExtractor


# Default embedding model for ChromaDB's default function
DEFAULT_MODEL = "all-MiniLM-L6-v2"

# Score boost for exact keyword/subheading matches
EXACT_MATCH_BOOST = 0.3


class RulesVectorStore:
    """Vector store for Pathfinder rules sections."""

    def __init__(
        self,
        persist_dir: str | Path = "vectordb",
        manifests_dir: str | Path = "manifests",
        embedding_model: str = DEFAULT_MODEL,
        collection_name: str = "pf_rules"
    ):
        """Initialize the vector store.

        Args:
            persist_dir: Directory to persist the ChromaDB database
            manifests_dir: Directory containing manifest JSON files
            embedding_model: Sentence-transformers model name for embeddings
            collection_name: Name of the ChromaDB collection
        """
        self.persist_dir = Path(persist_dir)
        self.manifests_dir = Path(manifests_dir)
        self.embedding_model = embedding_model
        self.collection_name = collection_name

        # Initialize ChromaDB with persistence
        self.client = chromadb.PersistentClient(path=str(self.persist_dir))

        # Use ChromaDB's default embedding function (uses onnx runtime, no torch needed)
        self.embedding_fn = embedding_functions.DefaultEmbeddingFunction()

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_fn,
            metadata={"description": "Pathfinder 1e rules sections"}
        )

        # Load keyword index from manifests
        self._keyword_index: dict[str, list[str]] | None = None
        self._subheading_index: dict[str, list[str]] | None = None
        self._section_metadata: dict[str, dict] | None = None

    def _load_keyword_index(self) -> None:
        """Load keyword and subheading indices from manifests."""
        if self._keyword_index is not None:
            return

        self._keyword_index = {}  # keyword -> list of section unique_ids
        self._subheading_index = {}  # subheading text -> list of section unique_ids
        self._section_metadata = {}  # unique_id -> section metadata

        for manifest_path in self.manifests_dir.glob("*.json"):
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)

            source_file = manifest["file"]

            for section in manifest["sections"]:
                unique_id = f"{source_file}::{section['id']}"

                # Store metadata
                self._section_metadata[unique_id] = {
                    "title": section["title"],
                    "description": section["description"],
                    "keywords": section["keywords"],
                    "source_file": source_file,
                    "anchor_heading": section["anchor_heading"],
                    "includes_subheadings": section.get("includes_subheadings", [])
                }

                # Index keywords (lowercase for matching)
                for keyword in section["keywords"]:
                    kw_lower = keyword.lower()
                    if kw_lower not in self._keyword_index:
                        self._keyword_index[kw_lower] = []
                    self._keyword_index[kw_lower].append(unique_id)

                # Index subheadings (extract text without # symbols)
                for subheading in section.get("includes_subheadings", []):
                    # Extract just the text part (remove markdown # and bold **)
                    text = re.sub(r'^[#\s*]+', '', subheading).strip('* ')
                    text_lower = text.lower()
                    if text_lower not in self._subheading_index:
                        self._subheading_index[text_lower] = []
                    self._subheading_index[text_lower].append(unique_id)

                # Also index the section title
                title_lower = section["title"].lower()
                if title_lower not in self._keyword_index:
                    self._keyword_index[title_lower] = []
                self._keyword_index[title_lower].append(unique_id)

    @staticmethod
    def _cosine_distance(vec1: list[float], vec2: list[float]) -> float:
        """Compute cosine distance between two vectors.

        Args:
            vec1: First embedding vector
            vec2: Second embedding vector

        Returns:
            Cosine distance (0 = identical, 2 = opposite)
        """
        import math
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        if norm1 == 0 or norm2 == 0:
            return 1.0
        cosine_similarity = dot_product / (norm1 * norm2)
        # Convert to distance (ChromaDB uses L2, but cosine distance works similarly)
        return 1 - cosine_similarity

    def _find_exact_matches(self, query_text: str) -> dict[str, float]:
        """Find sections with exact keyword or subheading matches.

        Args:
            query_text: The search query

        Returns:
            Dict mapping unique_id to match score (higher = better match)
        """
        self._load_keyword_index()

        matches = {}
        query_lower = query_text.lower()
        query_words = set(re.findall(r'\b\w+\b', query_lower))

        # Check for keyword matches
        for keyword, section_ids in self._keyword_index.items():
            # Full keyword appears in query
            if keyword in query_lower:
                for uid in section_ids:
                    matches[uid] = matches.get(uid, 0) + EXACT_MATCH_BOOST
            # Or query word matches keyword exactly
            elif keyword in query_words:
                for uid in section_ids:
                    matches[uid] = matches.get(uid, 0) + EXACT_MATCH_BOOST * 0.5

        # Check for subheading matches
        for subheading, section_ids in self._subheading_index.items():
            if subheading in query_lower:
                for uid in section_ids:
                    matches[uid] = matches.get(uid, 0) + EXACT_MATCH_BOOST

        return matches

    def index_sections(self, sections: list[Section], batch_size: int = 50) -> int:
        """Index sections into the vector store.

        Args:
            sections: List of Section objects to index
            batch_size: Number of sections to add at a time

        Returns:
            Number of sections indexed
        """
        # Clear existing data
        existing = self.collection.count()
        if existing > 0:
            print(f"Clearing {existing} existing documents...")
            # Get all IDs and delete them
            all_ids = self.collection.get()["ids"]
            if all_ids:
                self.collection.delete(ids=all_ids)

        print(f"Indexing {len(sections)} sections...")

        # Prepare documents for indexing
        # We embed a combination of title, description, keywords, and content
        # for better semantic matching
        for i in range(0, len(sections), batch_size):
            batch = sections[i:i + batch_size]

            ids = []
            documents = []
            metadatas = []

            for section in batch:
                # Create a rich document for embedding
                # Include title, description, keywords prominently
                keywords_str = ", ".join(section.keywords)
                doc_text = f"""Title: {section.title}
Description: {section.description}
Keywords: {keywords_str}

{section.content}"""

                # Use source_file + id to ensure uniqueness across files
                unique_id = f"{section.source_file}::{section.id}"
                ids.append(unique_id)
                documents.append(doc_text)
                metadatas.append({
                    "title": section.title,
                    "description": section.description,
                    "keywords": keywords_str,
                    "source_file": section.source_file,
                    "anchor_heading": section.anchor_heading,
                    "content_length": len(section.content)
                })

            self.collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )

            print(f"  Indexed {min(i + batch_size, len(sections))}/{len(sections)}")

        return len(sections)

    def query(
        self,
        query_text: str,
        n_results: int = 5,
        include_content: bool = True
    ) -> list[dict]:
        """Query the vector store for relevant sections.

        Combines semantic vector search with exact keyword/subheading matching.
        Exact matches boost the score of results.

        Args:
            query_text: The search query
            n_results: Maximum number of results to return
            include_content: Whether to include full content in results

        Returns:
            List of result dicts with id, title, description, score, and optionally content
        """
        # Get exact keyword/subheading matches
        exact_matches = self._find_exact_matches(query_text)

        # Fetch enough vector results to include most keyword matches
        # More results = better chance keyword matches have real semantic scores
        vector_n = max(n_results * 3, len(exact_matches) + n_results, 20)
        results = self.collection.query(
            query_texts=[query_text],
            n_results=vector_n,
            include=["documents", "metadatas", "distances"]
        )

        # Build results dict keyed by ID for deduplication
        results_by_id = {}

        for i in range(len(results["ids"][0])):
            uid = results["ids"][0][i]
            base_score = 1 / (1 + results["distances"][0][i])

            # Add exact match boost if applicable
            boost = exact_matches.get(uid, 0)
            final_score = base_score + boost

            results_by_id[uid] = {
                "id": uid,
                "title": results["metadatas"][0][i]["title"],
                "description": results["metadatas"][0][i]["description"],
                "keywords": results["metadatas"][0][i]["keywords"],
                "source_file": results["metadatas"][0][i]["source_file"],
                "distance": results["distances"][0][i],
                "score": final_score,
                "exact_match_boost": boost,
                "content": results["documents"][0][i] if include_content else None
            }

        # Add any exact matches not in vector results - compute their semantic scores
        missing_ids = [uid for uid in exact_matches if uid not in results_by_id]
        if missing_ids:
            # Get embeddings for missing docs to compute actual semantic similarity
            extra_results = self.collection.get(
                ids=missing_ids,
                include=["documents", "metadatas", "embeddings"]
            )

            # Get query embedding
            query_embedding = self.embedding_fn([query_text])[0]

            for i, uid in enumerate(extra_results["ids"]):
                boost = exact_matches[uid]

                # Compute cosine distance between query and document embedding
                doc_embedding = extra_results["embeddings"][i]
                distance = self._cosine_distance(query_embedding, doc_embedding)
                base_score = 1 / (1 + distance)

                results_by_id[uid] = {
                    "id": uid,
                    "title": extra_results["metadatas"][i]["title"],
                    "description": extra_results["metadatas"][i]["description"],
                    "keywords": extra_results["metadatas"][i]["keywords"],
                    "source_file": extra_results["metadatas"][i]["source_file"],
                    "distance": distance,
                    "score": base_score + boost,
                    "exact_match_boost": boost,
                    "content": extra_results["documents"][i] if include_content else None
                }

        # Sort by score and return top n
        sorted_results = sorted(results_by_id.values(), key=lambda x: x["score"], reverse=True)

        # Remove content=None if not requested
        if not include_content:
            for r in sorted_results:
                del r["content"]

        return sorted_results[:n_results]

    def get_stats(self) -> dict:
        """Get statistics about the vector store."""
        return {
            "collection_name": self.collection_name,
            "document_count": self.collection.count(),
            "embedding_model": self.embedding_model,
            "persist_dir": str(self.persist_dir)
        }


def build_index(
    rules_dir: str = "rules",
    manifests_dir: str = "manifests",
    persist_dir: str = "vectordb"
) -> RulesVectorStore:
    """Build the vector index from sections.

    Args:
        rules_dir: Directory containing markdown rules files
        manifests_dir: Directory containing manifest JSON files
        persist_dir: Directory to persist the vector database

    Returns:
        The initialized RulesVectorStore
    """
    # Load sections
    extractor = SectionExtractor(rules_dir=rules_dir, manifests_dir=manifests_dir)
    sections = extractor.load_all_sections()
    print(f"Loaded {len(sections)} sections")

    # Create and populate vector store
    store = RulesVectorStore(persist_dir=persist_dir)
    store.index_sections(sections)

    print(f"\nIndex built successfully!")
    print(f"Stats: {store.get_stats()}")

    return store


def main():
    """Build index and run demo queries."""
    import argparse

    parser = argparse.ArgumentParser(description="Build and query the rules vector store")
    parser.add_argument("--build", action="store_true", help="Build/rebuild the index")
    parser.add_argument("--query", "-q", type=str, help="Query to search for")
    parser.add_argument("--results", "-n", type=int, default=5, help="Number of results")

    args = parser.parse_args()

    if args.build:
        build_index()
        print()

    if args.query:
        store = RulesVectorStore()
        results = store.query(args.query, n_results=args.results)

        print(f"Query: {args.query}")
        print(f"Found {len(results)} results:\n")

        for i, result in enumerate(results, 1):
            boost = result.get('exact_match_boost', 0)
            boost_str = f" (+{boost:.2f} keyword boost)" if boost > 0 else ""
            print(f"{i}. [{result['source_file']}] {result['title']}")
            print(f"   Score: {result['score']:.3f}{boost_str}")
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
            print('  poetry run python vector_store.py -q "how does grappling work"')
            print('  poetry run python vector_store.py -q "attack of opportunity"')
            print('  poetry run python vector_store.py -q "what happens when I fall unconscious"')


if __name__ == "__main__":
    main()
