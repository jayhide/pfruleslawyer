"""Unit tests for the reranker module, focusing on LLM reranking."""

import pytest
from unittest.mock import MagicMock, patch

from pfruleslawyer.search.reranker import Reranker, RERANKER_MODELS


def make_result(id: str, title: str, description: str = "Test description") -> dict:
    """Create a mock search result."""
    return {
        "id": id,
        "title": title,
        "source_name": "Core Rulebook",
        "description": description,
        "score": 0.8,
    }


class TestExtractScoresFromResponse:
    """Tests for _extract_scores_from_response() method."""

    @pytest.fixture
    def reranker(self):
        """Create a reranker instance for testing static-like methods."""
        # Use ms-marco to avoid LLM initialization
        return Reranker("ms-marco")

    def test_extracts_valid_json(self, reranker):
        """Should extract scores from valid JSON."""
        text = '{"doc_0": 5, "doc_1": 3, "doc_2": 1}'
        scores = reranker._extract_scores_from_response(text, 3)
        assert scores == {"doc_0": 5.0, "doc_1": 3.0, "doc_2": 1.0}

    def test_extracts_json_with_surrounding_text(self, reranker):
        """Should extract JSON from response with surrounding text."""
        text = 'Here are the relevance scores:\n{"doc_0": 4, "doc_1": 2}\nThese ratings are...'
        scores = reranker._extract_scores_from_response(text, 2)
        assert scores == {"doc_0": 4.0, "doc_1": 2.0}

    def test_clamps_scores_to_valid_range(self, reranker):
        """Should clamp scores to 1-5 range."""
        text = '{"doc_0": 10, "doc_1": 0, "doc_2": -1}'
        scores = reranker._extract_scores_from_response(text, 3)
        assert scores["doc_0"] == 5.0  # Clamped from 10
        assert scores["doc_1"] == 1.0  # Clamped from 0
        assert scores["doc_2"] == 1.0  # Clamped from -1

    def test_handles_float_scores(self, reranker):
        """Should handle floating point scores."""
        text = '{"doc_0": 4.5, "doc_1": 2.3}'
        scores = reranker._extract_scores_from_response(text, 2)
        assert scores["doc_0"] == 4.5
        assert scores["doc_1"] == 2.3

    def test_fallback_regex_extraction(self, reranker):
        """Should fall back to regex for malformed JSON."""
        text = 'doc_0: 5\ndoc_1: 3\ndoc_2: 2'
        scores = reranker._extract_scores_from_response(text, 3)
        assert scores == {"doc_0": 5.0, "doc_1": 3.0, "doc_2": 2.0}

    def test_regex_with_quotes(self, reranker):
        """Should handle regex patterns with quoted doc IDs."""
        text = '"doc_0": 4, "doc_1": 2'
        scores = reranker._extract_scores_from_response(text, 2)
        assert scores == {"doc_0": 4.0, "doc_1": 2.0}

    def test_returns_empty_for_no_matches(self, reranker):
        """Should return empty dict when no scores found."""
        text = "I cannot rate these documents."
        scores = reranker._extract_scores_from_response(text, 3)
        assert scores == {}

    def test_ignores_non_doc_keys(self, reranker):
        """Should ignore keys that don't match doc_N pattern."""
        text = '{"doc_0": 5, "document_1": 3, "other": 2}'
        scores = reranker._extract_scores_from_response(text, 2)
        assert "doc_0" in scores
        assert "document_1" not in scores
        assert "other" not in scores


class TestFormatDocForLlm:
    """Tests for _format_doc_for_llm() static method."""

    def test_formats_complete_document(self):
        """Should format document with all fields."""
        result = {
            "title": "Grapple",
            "source_name": "Core Rulebook",
            "description": "Rules for grappling in combat",
        }
        formatted = Reranker._format_doc_for_llm("doc_0", result)
        assert formatted == "[doc_0] Grapple (Core Rulebook)\nRules for grappling in combat"

    def test_handles_missing_fields(self):
        """Should handle missing optional fields."""
        result = {"title": "Test"}
        formatted = Reranker._format_doc_for_llm("doc_0", result)
        assert "[doc_0] Test ()" in formatted


class TestRerankWithLlm:
    """Tests for _rerank_with_llm() method with mocked Anthropic client."""

    def test_successful_reranking(self):
        """Should add rerank_score to results on successful API call."""
        # Clear singleton cache to get fresh instance
        Reranker._instances.pop("llm-haiku", None)

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"doc_0": 5, "doc_1": 3}')]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("anthropic.Anthropic", return_value=mock_client):
            reranker = Reranker("llm-haiku")
            reranker._anthropic_client = mock_client

            results = [
                make_result("id1", "Grapple"),
                make_result("id2", "Attack of Opportunity"),
            ]

            reranked = reranker._rerank_with_llm("grapple rules", results)

        assert reranked[0]["rerank_score"] == 5.0
        assert reranked[1]["rerank_score"] == 3.0

    def test_api_error_returns_neutral_scores(self):
        """Should return neutral scores (3) on API errors."""
        Reranker._instances.pop("llm-haiku", None)

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API Error")

        with patch("anthropic.Anthropic", return_value=mock_client):
            reranker = Reranker("llm-haiku")
            reranker._anthropic_client = mock_client

            results = [
                make_result("id1", "Grapple"),
                make_result("id2", "Attack"),
            ]

            reranked = reranker._rerank_with_llm("grapple rules", results)

        assert reranked[0]["rerank_score"] == 3.0
        assert reranked[1]["rerank_score"] == 3.0

    def test_missing_scores_default_to_neutral(self):
        """Should default missing document scores to 3."""
        Reranker._instances.pop("llm-haiku", None)

        mock_response = MagicMock()
        # Only returns score for doc_0, not doc_1
        mock_response.content = [MagicMock(text='{"doc_0": 5}')]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("anthropic.Anthropic", return_value=mock_client):
            reranker = Reranker("llm-haiku")
            reranker._anthropic_client = mock_client

            results = [
                make_result("id1", "Grapple"),
                make_result("id2", "Attack"),
            ]

            reranked = reranker._rerank_with_llm("grapple rules", results)

        assert reranked[0]["rerank_score"] == 5.0
        assert reranked[1]["rerank_score"] == 3.0  # Default

    def test_empty_results_returns_empty(self):
        """Should handle empty results list."""
        Reranker._instances.pop("llm-haiku", None)

        with patch("anthropic.Anthropic"):
            reranker = Reranker("llm-haiku")
            reranked = reranker._rerank_with_llm("query", [])

        assert reranked == []


class TestComputeCombinedScores:
    """Tests for _compute_combined_scores() method."""

    @pytest.fixture
    def reranker(self):
        """Create a reranker instance."""
        return Reranker("ms-marco")

    def test_normalizes_scores_with_fixed_range(self, reranker):
        """Should normalize using provided score range."""
        results = [
            {"rerank_score": 5.0, "score": 0.8},
            {"rerank_score": 1.0, "score": 0.6},
        ]

        reranked = reranker._compute_combined_scores(results, score_range=(1.0, 5.0))

        # Score 5 normalizes to 1.0, score 1 normalizes to 0.0
        # With default weights (0.4 rerank, 0.6 retrieval):
        # doc1: 0.4*1.0 + 0.6*0.8 = 0.88
        # doc2: 0.4*0.0 + 0.6*0.6 = 0.36
        assert reranked[0]["combined_score"] == pytest.approx(0.88)
        assert reranked[1]["combined_score"] == pytest.approx(0.36)

    def test_sorts_by_combined_score(self, reranker):
        """Should sort results by combined score descending."""
        results = [
            {"rerank_score": 1.0, "score": 0.5, "title": "Low"},
            {"rerank_score": 5.0, "score": 0.5, "title": "High"},
        ]

        reranked = reranker._compute_combined_scores(results, score_range=(1.0, 5.0))

        assert reranked[0]["title"] == "High"
        assert reranked[1]["title"] == "Low"

    def test_uses_weight_getter_when_provided(self, reranker):
        """Should use weight_getter for category-specific weights."""

        def weight_getter(category):
            return 0.8 if category == "Spells" else 0.4

        results = [
            {"rerank_score": 5.0, "score": 0.5, "category": "Spells"},
            {"rerank_score": 5.0, "score": 0.5, "category": "Combat"},
        ]

        reranked = reranker._compute_combined_scores(
            results, weight_getter=weight_getter, score_range=(1.0, 5.0)
        )

        # Spells: 0.8*1.0 + 0.2*0.5 = 0.9
        # Combat: 0.4*1.0 + 0.6*0.5 = 0.7
        spells_result = next(r for r in reranked if r["category"] == "Spells")
        combat_result = next(r for r in reranked if r["category"] == "Combat")
        assert spells_result["combined_score"] == pytest.approx(0.9)
        assert combat_result["combined_score"] == pytest.approx(0.7)

    def test_empty_results_returns_empty(self, reranker):
        """Should handle empty results."""
        reranked = reranker._compute_combined_scores([])
        assert reranked == []


class TestRerankDispatch:
    """Tests for rerank() method dispatch logic."""

    def test_dispatches_to_llm_for_llm_haiku(self):
        """Should use LLM reranking for llm-haiku model."""
        Reranker._instances.pop("llm-haiku", None)

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"doc_0": 4}')]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("anthropic.Anthropic", return_value=mock_client):
            reranker = Reranker("llm-haiku")
            reranker._anthropic_client = mock_client

            results = [make_result("id1", "Test")]
            reranked = reranker.rerank("query", results)

        # Verify API was called
        mock_client.messages.create.assert_called_once()
        assert reranked[0]["rerank_score"] == 4.0

    def test_dispatches_to_cross_encoder_for_ms_marco(self):
        """Should use cross-encoder for ms-marco model."""
        Reranker._instances.pop("ms-marco", None)

        mock_model = MagicMock()
        mock_model.predict.return_value = [0.9]

        with patch("pfruleslawyer.search.reranker.CrossEncoder", return_value=mock_model):
            reranker = Reranker("ms-marco")
            reranker._model = mock_model

            results = [make_result("id1", "Test")]
            reranked = reranker.rerank("query", results)

        # Verify cross-encoder was called
        mock_model.predict.assert_called_once()


class TestRerankerModelRegistry:
    """Tests for reranker model registry."""

    def test_llm_haiku_in_registry(self):
        """llm-haiku should be registered."""
        assert "llm-haiku" in RERANKER_MODELS
        assert RERANKER_MODELS["llm-haiku"] == "claude-3-5-haiku-latest"

    def test_invalid_model_raises_error(self):
        """Should raise ValueError for unknown model."""
        Reranker._instances.pop("invalid-model", None)
        with pytest.raises(ValueError, match="Unknown reranker model"):
            Reranker("invalid-model")
