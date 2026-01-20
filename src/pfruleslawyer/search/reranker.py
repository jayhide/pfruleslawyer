"""Cross-encoder reranker for improving search result relevance."""

from sentence_transformers import CrossEncoder

# Available reranker models
RERANKER_MODELS = {
    "ms-marco": "cross-encoder/ms-marco-MiniLM-L-6-v2",
    "bge-large": "BAAI/bge-reranker-large",
}
DEFAULT_RERANKER = "ms-marco"

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

    def __new__(cls, model: str = DEFAULT_RERANKER) -> "Reranker":
        """Per-model singleton pattern to avoid loading models multiple times."""
        if model not in RERANKER_MODELS:
            raise ValueError(f"Unknown reranker model: {model}. Available: {list(RERANKER_MODELS.keys())}")
        if model not in cls._instances:
            instance = super().__new__(cls)
            instance._model_name = model
            instance._model = None
            cls._instances[model] = instance
        return cls._instances[model]

    def _ensure_model(self) -> CrossEncoder:
        """Lazy load the cross-encoder model."""
        if self._model is None:
            model_id = RERANKER_MODELS[self._model_name]
            self._model = CrossEncoder(model_id)
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
        weight_getter: "callable[[str], float] | None" = None
    ) -> list[dict]:
        """Rerank results using cross-encoder relevance scores.

        Uses title + description for scoring, which provides cleaner signal
        than full content (which may contain promotional text, links, etc.).

        Args:
            query: The search query
            results: List of result dicts from vector search
            weight_getter: Optional callable that takes a category name and returns
                          the rerank_weight for that category. If None, uses global
                          RERANK_WEIGHT constant.

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
