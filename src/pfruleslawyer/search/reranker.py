"""Cross-encoder reranker for improving search result relevance."""

import json
import logging
import re
import sys

import anthropic
from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)

# Available reranker models
RERANKER_MODELS = {
    "ms-marco": "cross-encoder/ms-marco-MiniLM-L-6-v2",
    "bge-large": "BAAI/bge-reranker-large",
    "llm-haiku": "claude-3-5-haiku-latest",  # LLM-based reranker
}
DEFAULT_RERANKER = "ms-marco"

# Prompt template for LLM-based reranking
LLM_RERANK_PROMPT = '''Rate each document's relevance to the search query on a 1-5 scale:
- 5: Directly answers the query with specific relevant rules
- 4: Highly relevant, contains key information for the query
- 3: Moderately relevant, related topic but may not fully answer
- 2: Tangentially related, mentions some query terms
- 1: Not relevant to the query

## Query
{query}

## Documents
{documents}

Return JSON mapping document IDs to scores:
{{"doc_0": 4, "doc_1": 2, ...}}'''

# Legacy constant for backward compatibility
RERANKER_MODEL = RERANKER_MODELS[DEFAULT_RERANKER]

# Reranking weights (must sum to 1.0)
# Higher RERANK_WEIGHT means cross-encoder has more influence on final ranking
# Higher RETRIEVAL_WEIGHT preserves more of the original semantic + keyword ranking
RERANK_WEIGHT = 0.4
RETRIEVAL_WEIGHT = 0.6


class Reranker:
    """Cross-encoder reranker for improving search result relevance."""

    _instances: dict[str, "Reranker"] = {}
    _model_name: str
    _model: CrossEncoder | None
    _anthropic_client: anthropic.Anthropic | None

    def __new__(cls, model: str = DEFAULT_RERANKER) -> "Reranker":
        """Per-model singleton pattern to avoid loading models multiple times."""
        if model not in RERANKER_MODELS:
            raise ValueError(f"Unknown reranker model: {model}. Available: {list(RERANKER_MODELS.keys())}")
        if model not in cls._instances:
            instance = super().__new__(cls)
            instance._model_name = model
            instance._model = None
            instance._anthropic_client = None
            cls._instances[model] = instance
        return cls._instances[model]

    def _ensure_model(self) -> CrossEncoder:
        """Lazy load the cross-encoder model."""
        if self._model is None:
            model_id = RERANKER_MODELS[self._model_name]
            self._model = CrossEncoder(model_id)
        return self._model

    def _ensure_anthropic_client(self) -> anthropic.Anthropic:
        """Lazy load the Anthropic client."""
        if self._anthropic_client is None:
            self._anthropic_client = anthropic.Anthropic()
        return self._anthropic_client

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

    @staticmethod
    def _format_doc_for_llm(doc_id: str, result: dict) -> str:
        """Format a document for inclusion in the LLM reranking prompt."""
        source = result.get('source_name', '')
        title = result.get('title', '')
        desc = result.get('description', '')
        return f"[{doc_id}] {title} ({source})\n{desc}"

    def _extract_scores_from_response(self, text: str, count: int) -> dict[str, float]:
        """Extract document scores from LLM response.

        Args:
            text: Raw LLM response text
            count: Number of documents expected

        Returns:
            Dict mapping doc IDs (e.g., "doc_0") to scores (1-5 scale)
        """
        # Try JSON parsing first
        try:
            # Find JSON object in response
            json_match = re.search(r'\{[^{}]*\}', text)
            if json_match:
                scores = json.loads(json_match.group())
                # Validate and clamp scores
                return {
                    k: max(1, min(5, float(v)))
                    for k, v in scores.items()
                    if k.startswith("doc_")
                }
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: regex extraction for patterns like "doc_0": 4 or doc_0: 4
        scores = {}
        pattern = r'"?(doc_\d+)"?\s*:\s*(\d+(?:\.\d+)?)'
        for match in re.finditer(pattern, text):
            doc_id = match.group(1)
            score = max(1, min(5, float(match.group(2))))
            scores[doc_id] = score

        return scores

    def _rerank_with_llm(self, query: str, results: list[dict]) -> list[dict]:
        """Rerank results using Claude Haiku LLM.

        Args:
            query: The search query
            results: List of result dicts from vector search

        Returns:
            Results with 'rerank_score' added (on 1-5 scale, to be normalized later)
        """
        if not results:
            return results

        # Format documents for the prompt
        doc_texts = []
        for i, result in enumerate(results):
            doc_texts.append(self._format_doc_for_llm(f"doc_{i}", result))
        documents = "\n\n".join(doc_texts)

        prompt = LLM_RERANK_PROMPT.format(query=query, documents=documents)

        try:
            client = self._ensure_anthropic_client()
            response = client.messages.create(
                model=RERANKER_MODELS["llm-haiku"],
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = response.content[0].text
            scores = self._extract_scores_from_response(response_text, len(results))

            # Add scores to results (default to 3 for missing)
            for i, result in enumerate(results):
                doc_id = f"doc_{i}"
                result["rerank_score"] = scores.get(doc_id, 3.0)

        except Exception as e:
            # Log warning and use neutral scores
            logger.warning(f"LLM reranking failed: {e}")
            print(f"Warning: LLM reranking failed ({e}), using neutral scores", file=sys.stderr)
            for result in results:
                result["rerank_score"] = 3.0

        return results

    def _compute_combined_scores(
        self,
        results: list[dict],
        weight_getter: "callable[[str], float] | None" = None,
        score_range: tuple[float, float] | None = None,
    ) -> list[dict]:
        """Normalize rerank scores and compute combined scores.

        Args:
            results: Results with 'rerank_score' already set
            weight_getter: Optional callable for category-specific weights
            score_range: Optional (min, max) for normalization. If None, computed from results.

        Returns:
            Results sorted by combined_score
        """
        if not results:
            return results

        # Get score range for normalization
        if score_range is None:
            scores = [r["rerank_score"] for r in results]
            min_score = min(scores)
            max_score = max(scores)
        else:
            min_score, max_score = score_range

        range_diff = max_score - min_score if max_score != min_score else 1.0

        for result in results:
            score = result["rerank_score"]
            normalized_rerank = (score - min_score) / range_diff

            # Get category-specific rerank weight or use global default
            if weight_getter:
                category = result.get("category", "Uncategorized")
                rerank_weight = weight_getter(category)
            else:
                rerank_weight = RERANK_WEIGHT
            retrieval_weight = 1.0 - rerank_weight

            # Combine with retrieval score (weighted average)
            retrieval_score = result.get("score", 0.5)
            result["combined_score"] = rerank_weight * normalized_rerank + retrieval_weight * retrieval_score

        return sorted(results, key=lambda x: x["combined_score"], reverse=True)

    def rerank(
        self,
        query: str,
        results: list[dict],
        weight_getter: "callable[[str], float] | None" = None
    ) -> list[dict]:
        """Rerank results using cross-encoder or LLM relevance scores.

        Uses title + description for scoring, which provides cleaner signal
        than full content (which may contain promotional text, links, etc.).

        Args:
            query: The search query
            results: List of result dicts from vector search
            weight_getter: Optional callable that takes a category name and returns
                          the rerank_weight for that category. If None, uses global
                          RERANK_WEIGHT constant.

        Returns:
            Results sorted by relevance score, with
            'rerank_score' added to each result
        """
        if not results:
            return results

        if self._model_name == "llm-haiku":
            # LLM-based reranking
            results = self._rerank_with_llm(query, results)
            # LLM scores are 1-5, normalize using fixed range
            return self._compute_combined_scores(results, weight_getter, score_range=(1.0, 5.0))
        else:
            # Cross-encoder reranking
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

            # Add rerank scores to results
            for result, score in zip(results, scores):
                result["rerank_score"] = float(score)

            # Compute combined scores (will normalize based on actual score range)
            return self._compute_combined_scores(results, weight_getter)
