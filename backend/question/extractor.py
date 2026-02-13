from __future__ import annotations

import re
import time
import logging

from backend.config import ActiveQuestionConfig
from backend.transcript.buffer import TranscriptBuffer

logger = logging.getLogger(__name__)

# Words that commonly start questions
_QUESTION_WORDS = frozenset({
    "what", "how", "why", "when", "where", "who", "which",
    "can", "could", "should", "would", "will", "do", "does",
    "did", "is", "are", "was", "were", "has", "have",
})

# Phrases that indicate a question even without ? or question-word start
_QUESTION_PHRASES = [
    "tell me about",
    "thoughts on",
    "any update",
    "any progress",
    "what about",
    "how about",
    "can you explain",
    "walk me through",
    "walk us through",
    "your take on",
    "opinion on",
    "status of",
    "update on",
]

# Regex to split text into sentences
_SENTENCE_SPLIT = re.compile(r'(?<=[.?!])\s+')


class ActiveQuestionExtractor:
    """Extracts the most likely active question from the rolling transcript."""

    def __init__(self, buffer: TranscriptBuffer, config: ActiveQuestionConfig):
        self._buffer = buffer
        self._config = config
        self._current_question: str | None = None
        self._last_change_time: float = 0.0
        self._last_version: int = -1
        self._question_history: list[dict] = []  # [{text, score, time}]
        self._seen_questions: set[str] = set()  # dedup by normalized text
        self._manual_question: str | None = None  # user-selected override

    @property
    def current_question(self) -> str | None:
        if self._manual_question is not None:
            return self._manual_question
        return self._current_question

    @property
    def question_history(self) -> list[dict]:
        return list(self._question_history)

    def select_question(self, text: str | None) -> None:
        """Manually select a question (or None to resume auto-detection)."""
        self._manual_question = text
        if text:
            logger.info("Manual question selected: %s", text)
        else:
            logger.info("Resumed auto question detection")

    def update(self) -> str | None:
        """Check for a new active question. Returns current question (may be unchanged)."""
        version = self._buffer.get_version()
        if version == self._last_version:
            return self.current_question
        self._last_version = version

        segments = self._buffer.get_segments()
        if not segments:
            return self.current_question

        # Filter to lookback window
        now = segments[-1].end_time
        cutoff = now - self._config.lookback_window_s
        recent = [s for s in segments if s.end_time >= cutoff]
        if not recent:
            return self.current_question

        # Split into sentences with timing info
        scored = self._score_sentences(recent)
        if not scored:
            return self.current_question

        # Add ALL qualifying questions to history (not just the best)
        for text, score in scored:
            norm = text.strip().lower()
            if norm not in self._seen_questions:
                self._seen_questions.add(norm)
                self._question_history.append({
                    "text": text,
                    "score": round(score, 2),
                    "time": time.monotonic(),
                })
                logger.info("New question detected: %s (score=%.2f)", text, score)

        # Pick the best for auto-detection
        best_text, best_score = max(scored, key=lambda x: x[1])

        if best_score < self._config.min_confidence:
            return self.current_question

        # Debounce: don't change question too frequently
        if best_text != self._current_question:
            elapsed = time.monotonic() - self._last_change_time
            if elapsed < self._config.debounce_interval_s:
                return self.current_question

            self._current_question = best_text
            self._last_change_time = time.monotonic()
            logger.info("Active question: %s", best_text)

        return self.current_question

    def _score_sentences(
        self, segments: list,
    ) -> list[tuple[str, float]]:
        """Score each sentence in the segments as a potential question."""
        # Build list of (sentence, relative_position) where position is 0..1
        sentences: list[tuple[str, float]] = []
        total = len(segments)
        for idx, seg in enumerate(segments):
            position = (idx + 1) / total  # 0..1, later = higher
            parts = _SENTENCE_SPLIT.split(seg.text.strip())
            for part in parts:
                part = part.strip()
                if len(part) < 5:
                    continue
                sentences.append((part, position))

        if not sentences:
            return []

        scored: list[tuple[str, float]] = []
        for text, position in sentences:
            score = self._score_sentence(text)
            if score <= 0:
                continue
            # Apply recency bias: sentences later in the window score higher
            score *= 0.5 + 0.5 * position
            scored.append((text, score))

        return scored

    @staticmethod
    def _score_sentence(text: str) -> float:
        """Score a single sentence as a question. Returns 0 if not a question."""
        score = 0.0
        lower = text.lower().strip()

        # Strong signal: ends with ?
        if text.rstrip().endswith("?"):
            score += 1.0

        # Medium signal: starts with a question word
        first_word = lower.split()[0] if lower.split() else ""
        if first_word in _QUESTION_WORDS:
            score += 0.6

        # Weak signal: contains question phrases
        for phrase in _QUESTION_PHRASES:
            if phrase in lower:
                score += 0.3
                break  # Only count once

        return score
