"""Vector store for semantic search over rules sections using ChromaDB."""

import json
import re
import chromadb
from chromadb.utils import embedding_functions
from pathlib import Path

import spacy
from nltk.stem import PorterStemmer
from sentence_transformers import CrossEncoder

from section_extractor import Section, SectionExtractor


# Default embedding model for ChromaDB's default function
DEFAULT_MODEL = "all-MiniLM-L6-v2"

# Cross-encoder model for re-ranking
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Score boosts for exact matches
KEYWORD_MATCH_BOOST = 0.2
SUBHEADING_MATCH_BOOST = 0.2
TITLE_MATCH_BOOST = 0.3

# Reranking weights (must sum to 1.0)
# Higher RERANK_WEIGHT means cross-encoder has more influence on final ranking
# Higher RETRIEVAL_WEIGHT preserves more of the original semantic + keyword ranking
RERANK_WEIGHT = 0.4
RETRIEVAL_WEIGHT = 0.6

# spaCy model for lemmatization
SPACY_MODEL = "en_core_web_sm"


class Lemmatizer:
    """Lemmatizer for normalizing words to their base form.

    Uses a hybrid approach: spaCy lemmatization followed by Porter stemming.
    This handles both common English words (via lemmatization) and domain-specific
    terms like 'polymorph' that spaCy doesn't recognize (via stemming).
    """

    _instance: "Lemmatizer | None" = None
    _nlp: spacy.Language | None = None
    _stemmer: PorterStemmer | None = None

    def __new__(cls) -> "Lemmatizer":
        """Singleton pattern to avoid loading model multiple times."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _ensure_model(self) -> spacy.Language:
        """Lazy load the spaCy model."""
        if self._nlp is None:
            # Disable unnecessary pipeline components for speed
            self._nlp = spacy.load(SPACY_MODEL, disable=["parser", "ner"])
        return self._nlp

    def _ensure_stemmer(self) -> PorterStemmer:
        """Lazy load the Porter stemmer."""
        if self._stemmer is None:
            self._stemmer = PorterStemmer()
        return self._stemmer

    def _normalize_word(self, token: spacy.tokens.Token) -> str:
        """Normalize a single token using lemmatization + stemming.

        Args:
            token: spaCy token

        Returns:
            Normalized form (lowercase)
        """
        stemmer = self._ensure_stemmer()
        # First get spaCy's lemma, then apply stemming for domain terms
        lemma = token.lemma_
        return stemmer.stem(lemma)

    def lemmatize(self, text: str) -> list[str]:
        """Lemmatize text and return list of normalized forms.

        Uses spaCy lemmatization followed by Porter stemming to handle
        both common English and domain-specific terms.

        Args:
            text: Text to lemmatize

        Returns:
            List of normalized forms (lowercase)
        """
        nlp = self._ensure_model()
        doc = nlp(text.lower())
        # Return normalized forms for words (skip punctuation, spaces)
        return [self._normalize_word(token) for token in doc if token.is_alpha]

    def lemmatize_word(self, word: str) -> str:
        """Lemmatize a single word.

        Args:
            word: Word to lemmatize

        Returns:
            Normalized form (lowercase)
        """
        nlp = self._ensure_model()
        doc = nlp(word.lower())
        # Return the normalized form of the first token, or the word itself if empty
        for token in doc:
            if token.is_alpha:
                return self._normalize_word(token)
        return word.lower()


class Reranker:
    """Cross-encoder reranker for improving search result relevance."""

    _instance: "Reranker | None" = None
    _model: CrossEncoder | None = None

    def __new__(cls) -> "Reranker":
        """Singleton pattern to avoid loading model multiple times."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _ensure_model(self) -> CrossEncoder:
        """Lazy load the cross-encoder model."""
        if self._model is None:
            self._model = CrossEncoder(RERANKER_MODEL)
        return self._model

    @staticmethod
    def _extract_rules_content(content: str) -> str:
        """Extract just the rules content, stripping metadata header.

        The indexed content has format:
            Title: ...
            Description: ...
            Keywords: ...

            <actual rules content>

        We strip the header to give the cross-encoder cleaner text.
        """
        if "\n\n" in content:
            parts = content.split("\n\n", 1)
            if len(parts) > 1:
                return parts[1]
        return content

    def rerank(
        self,
        query: str,
        results: list[dict],
    ) -> list[dict]:
        """Rerank results using cross-encoder relevance scores.

        Uses title + description for scoring, which provides cleaner signal
        than full content (which may contain promotional text, links, etc.).

        Args:
            query: The search query
            results: List of result dicts from vector search

        Returns:
            Results sorted by cross-encoder relevance score, with
            'rerank_score' added to each result
        """
        if not results:
            return results

        model = self._ensure_model()

        # Build query-document pairs for cross-encoder
        # Use source name + title + description for clean, focused text
        pairs = []
        for result in results:
            source = result.get('source_name', '')
            title = result.get('title', '')
            desc = result.get('description', '')
            doc_text = f"{title} ({source}) - {desc}"
            pairs.append((query, doc_text))

        # Get relevance scores from cross-encoder
        scores = model.predict(pairs)

        # Normalize rerank scores to 0-1 range for combining with retrieval score
        min_score = min(scores)
        max_score = max(scores)
        score_range = max_score - min_score if max_score != min_score else 1.0

        # Add rerank scores and compute combined score
        for result, score in zip(results, scores):
            result["rerank_score"] = float(score)
            # Normalize rerank score to 0-1 range
            normalized_rerank = (score - min_score) / score_range
            # Combine with retrieval score (weighted average)
            retrieval_score = result.get("score", 0.5)
            result["combined_score"] = RERANK_WEIGHT * normalized_rerank + RETRIEVAL_WEIGHT * retrieval_score

        return sorted(results, key=lambda x: x["combined_score"], reverse=True)


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
        self._title_index: dict[str, list[str]] | None = None
        self._section_metadata: dict[str, dict] | None = None

    def _load_keyword_index(self) -> None:
        """Load keyword and subheading indices from manifests.

        Uses lemmatization to normalize words, so "polymorphed" matches "polymorph".
        """
        if self._keyword_index is not None:
            return

        self._keyword_index = {}  # lemmatized keyword -> list of section unique_ids
        self._subheading_index = {}  # lemmatized subheading -> list of section unique_ids
        self._title_index = {}  # lemmatized title/anchor_heading -> list of section unique_ids
        self._section_metadata = {}  # unique_id -> section metadata

        lemmatizer = Lemmatizer()

        def _lemmatize_phrase(phrase: str) -> str:
            """Lemmatize a phrase, preserving word order."""
            lemmas = lemmatizer.lemmatize(phrase)
            return " ".join(lemmas) if lemmas else phrase.lower()

        for manifest_path in self.manifests_dir.glob("**/*.json"):
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)

            source_file = manifest["file"]
            # Use source_path to match vector store IDs (same logic as SectionExtractor)
            source_path = manifest.get("source_path", f"rules/{source_file}")

            source_name = manifest.get("source_name")
            if not source_name:
                source_name = source_file.replace(".md", "").replace("-", " ").title()

            for section in manifest["sections"]:
                unique_id = f"{source_path}::{section['id']}"

                # Store metadata
                self._section_metadata[unique_id] = {
                    "title": section["title"],
                    "description": section["description"],
                    "keywords": section["keywords"],
                    "source_file": source_file,
                    "source_name": source_name,
                    "anchor_heading": section["anchor_heading"],
                    "includes_subheadings": section.get("includes_subheadings", [])
                }

                # Index keywords (lemmatized for matching)
                for keyword in section["keywords"]:
                    kw_lemma = _lemmatize_phrase(keyword)
                    if kw_lemma not in self._keyword_index:
                        self._keyword_index[kw_lemma] = []
                    self._keyword_index[kw_lemma].append(unique_id)

                # Index subheadings (extract text without # symbols, then lemmatize)
                for subheading in section.get("includes_subheadings", []):
                    # Extract just the text part (remove markdown # and bold **)
                    text = re.sub(r'^[#\s*]+', '', subheading).strip('* ')
                    text_lemma = _lemmatize_phrase(text)
                    if text_lemma not in self._subheading_index:
                        self._subheading_index[text_lemma] = []
                    self._subheading_index[text_lemma].append(unique_id)

                # Index section title (lemmatized)
                title_lemma = _lemmatize_phrase(section["title"])
                if title_lemma not in self._title_index:
                    self._title_index[title_lemma] = []
                self._title_index[title_lemma].append(unique_id)

                # Index anchor_heading (extract text without # symbols, then lemmatize)
                anchor = section["anchor_heading"]
                anchor_text = re.sub(r'^[#\s*]+', '', anchor).strip('* ')
                anchor_lemma = _lemmatize_phrase(anchor_text)
                if anchor_lemma != title_lemma:  # Avoid duplicates
                    if anchor_lemma not in self._title_index:
                        self._title_index[anchor_lemma] = []
                    self._title_index[anchor_lemma].append(unique_id)

    @staticmethod
    def _fallback_source_name(source_path: str) -> str:
        """Generate a display name from source path when source_name is missing.

        Uses the same logic as preprocess_sections.get_source_name() for consistency.
        """
        # Import here to avoid circular imports
        from preprocess_sections import get_source_name
        return get_source_name(source_path)

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

    def _find_exact_matches(self, query_text: str) -> dict[str, dict[str, float]]:
        """Find sections with exact keyword or subheading matches.

        Uses lemmatization to match word variations (e.g., "polymorphed" matches "polymorph").

        Args:
            query_text: The search query

        Returns:
            Dict mapping unique_id to dict of match scores by type
            (keyword_boost, subheading_boost, title_boost)
        """
        self._load_keyword_index()

        matches: dict[str, dict[str, float]] = {}

        # Lemmatize the query for matching against lemmatized index
        lemmatizer = Lemmatizer()
        query_lemmas = lemmatizer.lemmatize(query_text)
        query_lemma_text = " ".join(query_lemmas)
        query_lemma_words = set(query_lemmas)

        def _ensure_entry(uid: str) -> dict[str, float]:
            if uid not in matches:
                matches[uid] = {"keyword_boost": 0, "subheading_boost": 0, "title_boost": 0}
            return matches[uid]

        def _matches_whole_word(phrase: str, text: str) -> bool:
            """Check if phrase appears as whole word(s) in text, not as substring.

            Also excludes matches that are part of hyphenated compounds like
            'non-magical' should not match 'magical'.
            """
            # Use negative lookbehind/lookahead for hyphens to avoid matching
            # parts of hyphenated words
            pattern = r'(?<!-)' + r'\b' + re.escape(phrase) + r'\b' + r'(?!-)'
            return bool(re.search(pattern, text))

        # Check for keyword matches (keywords are already lemmatized in the index)
        for keyword, section_ids in self._keyword_index.items():
            # Full keyword appears in lemmatized query as whole word(s)
            if _matches_whole_word(keyword, query_lemma_text):
                for uid in section_ids:
                    _ensure_entry(uid)["keyword_boost"] += KEYWORD_MATCH_BOOST
            # Or lemmatized query word matches keyword exactly
            elif keyword in query_lemma_words:
                for uid in section_ids:
                    _ensure_entry(uid)["keyword_boost"] += KEYWORD_MATCH_BOOST * 0.5

        # Check for subheading matches (subheadings are already lemmatized in the index)
        for subheading, section_ids in self._subheading_index.items():
            if _matches_whole_word(subheading, query_lemma_text):
                for uid in section_ids:
                    _ensure_entry(uid)["subheading_boost"] += SUBHEADING_MATCH_BOOST

        # Check for title/anchor_heading matches (titles are already lemmatized in the index)
        for title, section_ids in self._title_index.items():
            if _matches_whole_word(title, query_lemma_text):
                for uid in section_ids:
                    _ensure_entry(uid)["title_boost"] += TITLE_MATCH_BOOST
            elif title in query_lemma_words:
                for uid in section_ids:
                    _ensure_entry(uid)["title_boost"] += TITLE_MATCH_BOOST * 0.5

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
                    "source_name": section.source_name,
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
        include_content: bool = True,
        rerank: bool = True
    ) -> list[dict]:
        """Query the vector store for relevant sections.

        Combines semantic vector search with exact keyword/subheading matching.
        Optionally uses a cross-encoder to rerank results for better relevance.

        Args:
            query_text: The search query
            n_results: Maximum number of results to return
            include_content: Whether to include full content in results
            rerank: Whether to use cross-encoder reranking (default True)

        Returns:
            List of result dicts with id, title, description, score, and optionally content.
            If rerank=True, results include 'rerank_score' and are sorted by it.
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

        def _get_boosts(uid: str) -> dict[str, float]:
            """Get boost scores for a uid, defaulting to zeros."""
            return exact_matches.get(uid, {"keyword_boost": 0, "subheading_boost": 0, "title_boost": 0})

        for i in range(len(results["ids"][0])):
            uid = results["ids"][0][i]
            semantic_score = 1 / (1 + results["distances"][0][i])

            # Add exact match boosts if applicable
            boosts = _get_boosts(uid)
            total_boost = boosts["keyword_boost"] + boosts["subheading_boost"] + boosts["title_boost"]
            final_score = semantic_score + total_boost

            results_by_id[uid] = {
                "id": uid,
                "title": results["metadatas"][0][i]["title"],
                "description": results["metadatas"][0][i]["description"],
                "keywords": results["metadatas"][0][i]["keywords"],
                "source_file": results["metadatas"][0][i]["source_file"],
                "source_name": results["metadatas"][0][i].get("source_name") or self._fallback_source_name(results["metadatas"][0][i]["source_file"]),
                "distance": results["distances"][0][i],
                "score": final_score,
                "semantic_score": semantic_score,
                "keyword_boost": boosts["keyword_boost"],
                "subheading_boost": boosts["subheading_boost"],
                "title_boost": boosts["title_boost"],
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
                boosts = _get_boosts(uid)
                total_boost = boosts["keyword_boost"] + boosts["subheading_boost"] + boosts["title_boost"]

                # Compute cosine distance between query and document embedding
                doc_embedding = extra_results["embeddings"][i]
                distance = self._cosine_distance(query_embedding, doc_embedding)
                semantic_score = 1 / (1 + distance)

                results_by_id[uid] = {
                    "id": uid,
                    "title": extra_results["metadatas"][i]["title"],
                    "description": extra_results["metadatas"][i]["description"],
                    "keywords": extra_results["metadatas"][i]["keywords"],
                    "source_file": extra_results["metadatas"][i]["source_file"],
                    "source_name": extra_results["metadatas"][i].get("source_name") or self._fallback_source_name(extra_results["metadatas"][i]["source_file"]),
                    "distance": distance,
                    "score": semantic_score + total_boost,
                    "semantic_score": semantic_score,
                    "keyword_boost": boosts["keyword_boost"],
                    "subheading_boost": boosts["subheading_boost"],
                    "title_boost": boosts["title_boost"],
                    "content": extra_results["documents"][i] if include_content else None
                }

        # Sort by score and return top n
        sorted_results = sorted(results_by_id.values(), key=lambda x: x["score"], reverse=True)

        # Take top candidates for reranking (more than n_results to give reranker options)
        candidates = sorted_results[:n_results * 2] if rerank else sorted_results[:n_results]

        # Apply cross-encoder reranking if requested
        if rerank and candidates:
            reranker = Reranker()
            candidates = reranker.rerank(query_text, candidates)
            # Take top n after reranking
            candidates = candidates[:n_results]

        # Remove content=None if not requested
        if not include_content:
            for r in candidates:
                del r["content"]

        return candidates

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
    parser.add_argument("--no-rerank", action="store_true", help="Disable cross-encoder reranking")

    args = parser.parse_args()

    if args.build:
        build_index()
        print()

    if args.query:
        store = RulesVectorStore()
        rerank = not args.no_rerank
        results = store.query(args.query, n_results=args.results, rerank=rerank)

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
            print('  poetry run python vector_store.py -q "how does grappling work"')
            print('  poetry run python vector_store.py -q "attack of opportunity"')
            print('  poetry run python vector_store.py -q "what happens when I fall unconscious"')


if __name__ == "__main__":
    main()
