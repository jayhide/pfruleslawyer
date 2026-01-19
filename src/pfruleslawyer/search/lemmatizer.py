"""Lemmatizer for normalizing words to their base form."""

import spacy
from nltk.stem import PorterStemmer

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
