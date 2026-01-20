"""Vector store for semantic search over rules sections using ChromaDB."""

import json
import re
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

from pfruleslawyer.core import Section
from pfruleslawyer.extraction import SectionExtractor
from .lemmatizer import Lemmatizer
from .reranker import Reranker, RERANK_WEIGHT, DEFAULT_RERANKER

# Default embedding model for ChromaDB's default function
DEFAULT_MODEL = "all-MiniLM-L6-v2"

# Score boosts for exact matches
KEYWORD_MATCH_BOOST = 0.2
SUBHEADING_MATCH_BOOST = 0.2
TITLE_MATCH_BOOST = 0.3

# Default paths relative to project root
DEFAULT_PERSIST_DIR = Path(__file__).parent.parent.parent.parent / "data" / "vectordb"
DEFAULT_MANIFESTS_DIR = Path(__file__).parent.parent.parent.parent / "data" / "manifests"
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "config" / "preprocess_config.json"


def strip_markdown_links(text: str) -> str:
    """Strip markdown links from text, keeping only the link text.

    Converts [link text](url) to just "link text" and removes bare URLs.
    This produces cleaner text for semantic embedding.

    Args:
        text: Markdown text potentially containing links

    Returns:
        Text with links stripped
    """
    # Replace [text](url) with just text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Remove bare URLs (http/https)
    text = re.sub(r'https?://\S+', '', text)
    # Remove image references ![alt](url)
    text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'\1', text)
    return text


def fragment_to_heading_text(fragment: str) -> str:
    """Convert URL fragment to searchable heading text.

    Handles common fragment patterns from d20pfsrd.com:
    - 'TOC-Threatened-Squares' -> 'threatened squares'
    - 'class_skills' -> 'class skills'

    Args:
        fragment: URL fragment (without the # prefix)

    Returns:
        Normalized heading text (lowercase)
    """
    # Remove common prefixes
    text = fragment
    if text.upper().startswith("TOC-"):
        text = text[4:]

    # Replace hyphens and underscores with spaces
    text = text.replace("-", " ").replace("_", " ")

    # Normalize whitespace and lowercase
    return " ".join(text.lower().split())


def normalize_url(url: str) -> tuple[str, str | None]:
    """Parse and normalize a URL, extracting base and fragment.

    Args:
        url: Full URL, possibly with fragment

    Returns:
        Tuple of (base_url, fragment) where fragment may be None
    """
    # Split on # to get fragment
    if "#" in url:
        base, fragment = url.split("#", 1)
    else:
        base, fragment = url, None

    # Normalize base URL - ensure consistent trailing slash
    base = base.rstrip("/") + "/"

    return base, fragment


def extract_headings_from_content(content: str) -> list[tuple[str, str | None]]:
    """Extract all headings from markdown content with their anchor IDs.

    Args:
        content: Markdown content

    Returns:
        List of (heading_text, anchor_id) tuples. anchor_id may be None.
    """
    headings = []
    for line in content.split('\n'):
        # Match markdown headings (## to ######)
        match = re.match(r'^(#{2,6})\s+(.+)$', line)
        if match:
            heading_text = match.group(2).strip()
            # Extract anchor ID if present: "Heading Text {#anchor_id}"
            anchor_match = re.search(r'\{#([^}]+)\}\s*$', heading_text)
            if anchor_match:
                anchor_id = anchor_match.group(1)
                # Remove anchor from heading text for display matching
                heading_text = heading_text[:anchor_match.start()].strip()
            else:
                anchor_id = None
            headings.append((heading_text, anchor_id))
    return headings


class RulesVectorStore:
    """Vector store for Pathfinder rules sections."""

    def __init__(
        self,
        persist_dir: str | Path | None = None,
        manifests_dir: str | Path | None = None,
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
        self.persist_dir = Path(persist_dir) if persist_dir else DEFAULT_PERSIST_DIR
        self.manifests_dir = Path(manifests_dir) if manifests_dir else DEFAULT_MANIFESTS_DIR
        self.embedding_model = embedding_model
        self.collection_name = collection_name

        # Ensure persist_dir exists
        self.persist_dir.mkdir(parents=True, exist_ok=True)

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
        self._url_index: dict[str, list[str]] | None = None  # base URL -> section unique_ids
        self._heading_to_section: dict[str, dict[str, str]] | None = None  # base URL -> {heading_text: unique_id}
        self._anchor_id_index: dict[str, dict[str, str]] | None = None  # base URL -> {anchor_id: unique_id}

        # Category-specific search weights
        self._category_weights: dict[str, dict[str, float]] | None = None
        self._config_path = DEFAULT_CONFIG_PATH

        # Metadata-only sections (categories with semantic_weight=0)
        # These are not embedded, only stored for title/keyword matching
        self._metadata_only_sections: dict[str, dict] | None = None
        self._metadata_only_path = self.persist_dir / "metadata_only.json"

    def _load_category_weights(self) -> None:
        """Load category weights from config file.

        Weights control how different scoring factors contribute to search ranking
        per category. Categories without explicit weights use the '_default' weights.
        """
        if self._category_weights is not None:
            return

        # Default weights (same as original global constants)
        self._category_weights = {
            "_default": {
                "semantic_weight": 1.0,
                "keyword_boost": KEYWORD_MATCH_BOOST,
                "subheading_boost": SUBHEADING_MATCH_BOOST,
                "title_boost": TITLE_MATCH_BOOST,
                "rerank_weight": RERANK_WEIGHT
            }
        }

        # Try to load from config file
        if self._config_path.exists():
            try:
                with open(self._config_path, encoding="utf-8") as f:
                    config = json.load(f)
                if "category_weights" in config:
                    # Merge config weights with defaults
                    for category, weights in config["category_weights"].items():
                        self._category_weights[category] = weights
            except (json.JSONDecodeError, KeyError):
                pass  # Use defaults if config is invalid

    def _get_weights_for_category(self, category: str) -> dict[str, float]:
        """Get search weights for a category.

        Args:
            category: The category name (e.g., "Spells", "Skills")

        Returns:
            Dict with weight values for semantic_weight, keyword_boost,
            subheading_boost, title_boost, and rerank_weight
        """
        self._load_category_weights()

        if category in self._category_weights:
            return self._category_weights[category]
        return self._category_weights["_default"]

    def _load_metadata_only_sections(self) -> None:
        """Load metadata-only sections from persistence.

        These are sections from categories with semantic_weight=0 that don't
        need embeddings but still need to be searchable by title/keyword.
        """
        if self._metadata_only_sections is not None:
            return

        self._metadata_only_sections = {}

        if self._metadata_only_path.exists():
            try:
                with open(self._metadata_only_path, encoding="utf-8") as f:
                    self._metadata_only_sections = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass  # Start with empty dict if file is invalid

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
        self._url_index = {}  # normalized base URL -> list of section unique_ids
        self._heading_to_section = {}  # normalized base URL -> {normalized_heading: unique_id}
        self._anchor_id_index = {}  # normalized base URL -> {anchor_id: unique_id}

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
                    "category": manifest.get("category", "Uncategorized")
                }

                # Index keywords (lemmatized for matching)
                for keyword in section["keywords"]:
                    kw_lemma = _lemmatize_phrase(keyword)
                    if kw_lemma not in self._keyword_index:
                        self._keyword_index[kw_lemma] = []
                    self._keyword_index[kw_lemma].append(unique_id)

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

                # Index by URL for link resolution
                if source_path.startswith("http"):
                    base_url, _ = normalize_url(source_path)

                    # Add to URL index
                    if base_url not in self._url_index:
                        self._url_index[base_url] = []
                    self._url_index[base_url].append(unique_id)

                    # Build heading-to-section mapping from actual content
                    if base_url not in self._heading_to_section:
                        self._heading_to_section[base_url] = {}
                    if base_url not in self._anchor_id_index:
                        self._anchor_id_index[base_url] = {}

                    # Get content from ChromaDB or metadata-only storage
                    self._load_metadata_only_sections()
                    content = ""
                    if unique_id in self._metadata_only_sections:
                        content = self._metadata_only_sections[unique_id].get("content", "")
                    else:
                        result = self.collection.get(ids=[unique_id], include=["metadatas"])
                        if result["ids"] and result["metadatas"]:
                            content = result["metadatas"][0].get("content", "")

                    if content:
                        # Extract headings with anchor IDs from content
                        headings = extract_headings_from_content(content)
                        for heading_text, anchor_id in headings:
                            # Index by heading text (normalized)
                            normalized_heading = heading_text.lower()
                            self._heading_to_section[base_url][normalized_heading] = unique_id

                            # Index by anchor ID if present
                            if anchor_id:
                                self._anchor_id_index[base_url][anchor_id] = unique_id

                            # Index subheading for search (lemmatized)
                            heading_lemma = _lemmatize_phrase(heading_text)
                            if heading_lemma not in self._subheading_index:
                                self._subheading_index[heading_lemma] = []
                            self._subheading_index[heading_lemma].append(unique_id)

    @staticmethod
    def _fallback_source_name(source_path: str) -> str:
        """Generate a display name from source path when source_name is missing.

        Uses the same logic as processor.get_source_name() for consistency.
        """
        from pfruleslawyer.preprocessing import get_source_name
        return get_source_name(source_path)

    def resolve_link(self, url: str) -> dict:
        """Resolve a URL (with optional fragment) to a section.

        Used to "follow" links in rules content. Handles URLs with fragments
        like #TOC-Threatened-Squares by matching to the appropriate section.

        Args:
            url: Full URL, optionally with fragment (e.g., #TOC-Something)

        Returns:
            Dict with section data including 'content', or error dict with 'error' key
        """
        self._load_keyword_index()

        base_url, fragment = normalize_url(url)

        # Check if we have this URL in our index
        if base_url not in self._url_index:
            # Try without trailing slash
            alt_url = base_url.rstrip("/")
            if alt_url + "/" not in self._url_index and alt_url not in self._url_index:
                return {"error": "URL not in database", "url": url}

        section_ids = self._url_index.get(base_url, [])
        if not section_ids:
            return {"error": "URL not in database", "url": url}

        # If no fragment, return the first section for this URL
        if not fragment:
            unique_id = section_ids[0]
            return self._get_section_result(unique_id)

        # Try direct anchor ID lookup first (most reliable)
        anchor_map = self._anchor_id_index.get(base_url, {})

        # Try exact match on anchor ID
        if fragment in anchor_map:
            return self._get_section_result(anchor_map[fragment])

        # Try normalized fragment: strip TOC- prefix, convert to lowercase with underscores
        normalized_fragment = fragment
        if normalized_fragment.upper().startswith("TOC-"):
            normalized_fragment = normalized_fragment[4:]
        normalized_fragment = normalized_fragment.lower().replace("-", "_")

        if normalized_fragment in anchor_map:
            return self._get_section_result(anchor_map[normalized_fragment])

        # Fallback: Convert fragment to heading text and look up
        heading_text = fragment_to_heading_text(fragment)
        heading_map = self._heading_to_section.get(base_url, {})

        # Try exact match first
        if heading_text in heading_map:
            unique_id = heading_map[heading_text]
            return self._get_section_result(unique_id)

        # Try partial/fuzzy match - find heading containing the fragment text
        for heading, uid in heading_map.items():
            if heading_text in heading or heading in heading_text:
                return self._get_section_result(uid)

        # Fragment not found - return first section with a note
        return {
            "error": "Fragment not found",
            "url": url,
            "fragment": fragment,
            "available_sections": [self._section_metadata[sid]["title"] for sid in section_ids[:5]]
        }

    def _get_section_result(self, unique_id: str) -> dict:
        """Get full section data for a unique_id.

        Args:
            unique_id: Section unique ID (source_path::section_id)

        Returns:
            Dict with section metadata and content
        """
        # Get metadata from our index
        metadata = self._section_metadata.get(unique_id)
        if not metadata:
            return {"error": "Section not found", "id": unique_id}

        # Get full content from ChromaDB
        result = self.collection.get(
            ids=[unique_id],
            include=["metadatas"]
        )

        if not result["ids"]:
            return {"error": "Section not in vector store", "id": unique_id}

        # Return content from metadata (original with links)
        content = result["metadatas"][0].get("content", "")

        return {
            "id": unique_id,
            "title": metadata["title"],
            "description": metadata["description"],
            "source_name": metadata["source_name"],
            "anchor_heading": metadata["anchor_heading"],
            "content": content
        }

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
            Dict mapping unique_id to dict of raw match counts by type
            (keyword_matches, subheading_matches, title_matches).
            These are raw counts, not weighted - weights are applied per-category
            in the query() method.
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
                matches[uid] = {"keyword_matches": 0, "subheading_matches": 0, "title_matches": 0}
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
                    _ensure_entry(uid)["keyword_matches"] += 1.0
            # Or lemmatized query word matches keyword exactly (half weight)
            elif keyword in query_lemma_words:
                for uid in section_ids:
                    _ensure_entry(uid)["keyword_matches"] += 0.5

        # Check for subheading matches (subheadings are already lemmatized in the index)
        for subheading, section_ids in self._subheading_index.items():
            if _matches_whole_word(subheading, query_lemma_text):
                for uid in section_ids:
                    _ensure_entry(uid)["subheading_matches"] += 1.0

        # Check for title/anchor_heading matches (titles are already lemmatized in the index)
        for title, section_ids in self._title_index.items():
            if _matches_whole_word(title, query_lemma_text):
                for uid in section_ids:
                    _ensure_entry(uid)["title_matches"] += 1.0
            elif title in query_lemma_words:
                for uid in section_ids:
                    _ensure_entry(uid)["title_matches"] += 0.5

        return matches

    def index_sections(self, sections: list[Section], batch_size: int = 50) -> int:
        """Index sections into the vector store.

        Sections from categories with semantic_weight=0 are stored as metadata-only
        (no embeddings computed), while other sections are embedded in ChromaDB.

        Args:
            sections: List of Section objects to index
            batch_size: Number of sections to add at a time

        Returns:
            Number of sections indexed
        """
        # Load category weights to determine which sections need embeddings
        self._load_category_weights()

        # Split sections by whether they need semantic embeddings
        semantic_sections = []
        metadata_only_sections = []

        for section in sections:
            weights = self._get_weights_for_category(section.category)
            if weights.get("semantic_weight", 1.0) == 0:
                metadata_only_sections.append(section)
            else:
                semantic_sections.append(section)

        print(f"Indexing {len(sections)} sections ({len(semantic_sections)} semantic, {len(metadata_only_sections)} metadata-only)...")

        # Clear existing ChromaDB data
        existing = self.collection.count()
        if existing > 0:
            print(f"Clearing {existing} existing documents from ChromaDB...")
            all_ids = self.collection.get()["ids"]
            if all_ids:
                self.collection.delete(ids=all_ids)

        # Clear existing metadata-only sections
        self._metadata_only_sections = {}

        # Index semantic sections to ChromaDB (with embeddings)
        for i in range(0, len(semantic_sections), batch_size):
            batch = semantic_sections[i:i + batch_size]

            ids = []
            documents = []
            metadatas = []

            for section in batch:
                keywords_str = ", ".join(section.keywords)
                stripped_content = strip_markdown_links(section.content)
                doc_text = f"""Title: {section.title}
Description: {section.description}
Keywords: {keywords_str}

{stripped_content}"""

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
                    "content": section.content,
                    "content_length": len(section.content),
                    "category": section.category
                })

            self.collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )

            print(f"  Indexed {min(i + batch_size, len(semantic_sections))}/{len(semantic_sections)}")

        # Store metadata-only sections (no embedding computation)
        print(f"Storing {len(metadata_only_sections)} metadata-only sections...")
        for section in metadata_only_sections:
            unique_id = f"{section.source_file}::{section.id}"
            self._metadata_only_sections[unique_id] = {
                "title": section.title,
                "description": section.description,
                "keywords": ", ".join(section.keywords),
                "source_file": section.source_file,
                "source_name": section.source_name,
                "anchor_heading": section.anchor_heading,
                "content": section.content,
                "content_length": len(section.content),
                "category": section.category
            }

        # Persist metadata-only sections to disk
        with open(self._metadata_only_path, "w", encoding="utf-8") as f:
            json.dump(self._metadata_only_sections, f)

        return len(sections)

    def query(
        self,
        query_text: str,
        n_results: int = 5,
        include_content: bool = True,
        rerank: bool = True,
        reranker_model: str | None = None
    ) -> list[dict]:
        """Query the vector store for relevant sections.

        Combines semantic vector search with exact keyword/subheading matching.
        Optionally uses a cross-encoder to rerank results for better relevance.

        Args:
            query_text: The search query
            n_results: Maximum number of results to return
            include_content: Whether to include full content in results
            rerank: Whether to use cross-encoder reranking (default True)
            reranker_model: Reranker model to use (default: ms-marco)

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

        def _get_raw_matches(uid: str) -> dict[str, float]:
            """Get raw match counts for a uid, defaulting to zeros."""
            return exact_matches.get(uid, {"keyword_matches": 0, "subheading_matches": 0, "title_matches": 0})

        def _apply_category_weights(
            semantic_score: float,
            raw_matches: dict[str, float],
            category: str
        ) -> tuple[float, float, float, float, float]:
            """Apply category-specific weights to compute final score.

            Returns:
                Tuple of (final_score, weighted_semantic, keyword_boost, subheading_boost, title_boost)
            """
            weights = self._get_weights_for_category(category)

            # Apply weights to each component
            weighted_semantic = semantic_score * weights.get("semantic_weight", 1.0)
            keyword_boost = raw_matches["keyword_matches"] * weights.get("keyword_boost", KEYWORD_MATCH_BOOST)
            subheading_boost = raw_matches["subheading_matches"] * weights.get("subheading_boost", SUBHEADING_MATCH_BOOST)
            title_boost = raw_matches["title_matches"] * weights.get("title_boost", TITLE_MATCH_BOOST)

            final_score = weighted_semantic + keyword_boost + subheading_boost + title_boost
            return final_score, weighted_semantic, keyword_boost, subheading_boost, title_boost

        for i in range(len(results["ids"][0])):
            uid = results["ids"][0][i]
            raw_semantic_score = 1 / (1 + results["distances"][0][i])
            category = results["metadatas"][0][i].get("category", "Uncategorized")

            # Apply category-specific weights
            raw_matches = _get_raw_matches(uid)
            final_score, weighted_semantic, keyword_boost, subheading_boost, title_boost = _apply_category_weights(
                raw_semantic_score, raw_matches, category
            )

            results_by_id[uid] = {
                "id": uid,
                "title": results["metadatas"][0][i]["title"],
                "description": results["metadatas"][0][i]["description"],
                "keywords": results["metadatas"][0][i]["keywords"],
                "source_file": results["metadatas"][0][i]["source_file"],
                "source_name": results["metadatas"][0][i].get("source_name") or self._fallback_source_name(results["metadatas"][0][i]["source_file"]),
                "category": category,
                "distance": results["distances"][0][i],
                "score": final_score,
                "semantic_score": weighted_semantic,
                "keyword_boost": keyword_boost,
                "subheading_boost": subheading_boost,
                "title_boost": title_boost,
                # Return original content with links from metadata
                "content": results["metadatas"][0][i].get("content") if include_content else None
            }

        # Add any exact matches not in vector results
        missing_ids = [uid for uid in exact_matches if uid not in results_by_id]
        if missing_ids:
            # Load metadata-only sections
            self._load_metadata_only_sections()

            # Separate into metadata-only vs ChromaDB sections
            metadata_only_ids = [uid for uid in missing_ids if uid in self._metadata_only_sections]
            chromadb_ids = [uid for uid in missing_ids if uid not in self._metadata_only_sections]

            # Handle metadata-only sections (no embedding lookup needed)
            for uid in metadata_only_ids:
                metadata = self._metadata_only_sections[uid]
                category = metadata.get("category", "Uncategorized")

                # Apply category-specific weights (semantic_weight=0 for these)
                raw_matches = _get_raw_matches(uid)
                final_score, weighted_semantic, keyword_boost, subheading_boost, title_boost = _apply_category_weights(
                    0.0, raw_matches, category  # No semantic score for metadata-only
                )

                results_by_id[uid] = {
                    "id": uid,
                    "title": metadata["title"],
                    "description": metadata["description"],
                    "keywords": metadata["keywords"],
                    "source_file": metadata["source_file"],
                    "source_name": metadata.get("source_name") or self._fallback_source_name(metadata["source_file"]),
                    "category": category,
                    "distance": float("inf"),  # No embedding distance
                    "score": final_score,
                    "semantic_score": weighted_semantic,
                    "keyword_boost": keyword_boost,
                    "subheading_boost": subheading_boost,
                    "title_boost": title_boost,
                    "content": metadata.get("content") if include_content else None
                }

            # Handle ChromaDB sections - compute their semantic scores
            if chromadb_ids:
                extra_results = self.collection.get(
                    ids=chromadb_ids,
                    include=["documents", "metadatas", "embeddings"]
                )

                # Get query embedding
                query_embedding = self.embedding_fn([query_text])[0]

                for i, uid in enumerate(extra_results["ids"]):
                    # Compute cosine distance between query and document embedding
                    doc_embedding = extra_results["embeddings"][i]
                    distance = self._cosine_distance(query_embedding, doc_embedding)
                    raw_semantic_score = 1 / (1 + distance)

                    category = extra_results["metadatas"][i].get("category", "Uncategorized")

                    # Apply category-specific weights
                    raw_matches = _get_raw_matches(uid)
                    final_score, weighted_semantic, keyword_boost, subheading_boost, title_boost = _apply_category_weights(
                        raw_semantic_score, raw_matches, category
                    )

                    results_by_id[uid] = {
                        "id": uid,
                        "title": extra_results["metadatas"][i]["title"],
                        "description": extra_results["metadatas"][i]["description"],
                        "keywords": extra_results["metadatas"][i]["keywords"],
                        "source_file": extra_results["metadatas"][i]["source_file"],
                        "source_name": extra_results["metadatas"][i].get("source_name") or self._fallback_source_name(extra_results["metadatas"][i]["source_file"]),
                        "category": category,
                        "distance": distance,
                        "score": final_score,
                        "semantic_score": weighted_semantic,
                        "keyword_boost": keyword_boost,
                        "subheading_boost": subheading_boost,
                        "title_boost": title_boost,
                        "content": extra_results["metadatas"][i].get("content") if include_content else None
                    }

        # Sort by score and return top n
        sorted_results = sorted(results_by_id.values(), key=lambda x: x["score"], reverse=True)

        # Filter out results with zero retrieval score - they weren't truly retrieved
        # (e.g., categories with semantic_weight=0 that had no title/keyword match)
        sorted_results = [r for r in sorted_results if r["score"] > 0]

        # Take top candidates for reranking (more than n_results to give reranker options)
        candidates = sorted_results[:n_results * 2] if rerank else sorted_results[:n_results]

        # Apply cross-encoder reranking if requested
        if rerank and candidates:
            reranker = Reranker(reranker_model or DEFAULT_RERANKER)

            # Create weight getter for category-specific rerank weights
            def get_rerank_weight(category: str) -> float:
                weights = self._get_weights_for_category(category)
                return weights.get("rerank_weight", RERANK_WEIGHT)

            candidates = reranker.rerank(query_text, candidates, weight_getter=get_rerank_weight)
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
    rules_dir: str | Path | None = None,
    manifests_dir: str | Path | None = None,
    persist_dir: str | Path | None = None
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
    store = RulesVectorStore(persist_dir=persist_dir, manifests_dir=manifests_dir)
    store.index_sections(sections)

    print(f"\nIndex built successfully!")
    print(f"Stats: {store.get_stats()}")

    return store
