from __future__ import annotations

import logging
import re
import time

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
        self._candidate_question: str | None = None  # best question before debounce
        self._manual_question: str | None = None  # user-selected override
        self._manual_set_time: float | None = None

    def _maybe_expire_manual(self) -> None:
        if self._manual_question is None or self._manual_set_time is None:
            return
        try:
            timeout_s = float(getattr(self._config, "manual_override_timeout_s", 0.0) or 0.0)
        except Exception:
            timeout_s = 0.0
        if timeout_s <= 0:
            return
        if (time.monotonic() - self._manual_set_time) >= timeout_s:
            logger.info("Manual question override expired; resuming auto")
            self._manual_question = None
            self._manual_set_time = None

    @property
    def current_question(self) -> str | None:
        self._maybe_expire_manual()
        if self._manual_question is not None:
            return self._manual_question
        return self._current_question

    @property
    def is_manual_override(self) -> bool:
        """Whether a manual question override is active."""
        return self._manual_question is not None

    @property
    def manual_question(self) -> str | None:
        """The manually set question, or None if auto-detecting."""
        return self._manual_question

    @property
    def question_history(self) -> list[dict]:
        """Return question history with staleness flags and ranked by score."""
        now = time.monotonic()
        staleness_threshold = self._config.question_staleness_s
        
        # Annotate questions with staleness
        annotated = []
        for q in self._question_history:
            age = now - q.get("time", 0)
            is_stale = age > staleness_threshold
            annotated.append({
                **q,
                "stale": is_stale,
                "age": age,
            })
        
        # Sort by score (descending), then by recency (newer first for ties)
        annotated.sort(key=lambda x: (-x.get("score", 0), -x.get("time", 0)))
        
        # Return top N questions
        top_n = self._config.track_top_n
        return annotated[:top_n] if top_n > 0 else annotated

    def select_question(self, text: str | None) -> None:
        """Manually select a question (or None to resume auto-detection)."""
        self._manual_question = text
        self._manual_set_time = time.monotonic() if text else None

        if text:
            # Ensure manual entries show up in history too.
            norm = text.strip().lower()
            if norm and norm not in self._seen_questions:
                self._seen_questions.add(norm)
                self._question_history.append({
                    "text": text,
                    "score": 1.0,
                    "time": time.monotonic(),
                })
            logger.info("Manual question selected: %s", text)
        else:
            logger.info("Resumed auto question detection")

    @property
    def candidate_question(self):
        """Best-scoring question before debounce fires."""
        return self._candidate_question

    def update(self) -> str | None:
        """Check for a new active question. Returns current question (may be unchanged)."""
        self._maybe_expire_manual()
        version = self._buffer.get_version()
        if version == self._last_version:
            logger.debug("[QuestionExtractor] No transcript version change (version=%d)", version)
            return self.current_question
        self._last_version = version
        logger.debug("[QuestionExtractor] Transcript version changed to %d", version)

        segments = self._buffer.get_segments()
        if not segments:
            logger.debug("[QuestionExtractor] No transcript segments available")
            return self.current_question
        logger.debug("[QuestionExtractor] Processing %d transcript segments", len(segments))

        # Filter to lookback window
        now = segments[-1].end_time
        cutoff = now - self._config.lookback_window_s
        recent = [s for s in segments if s.end_time >= cutoff]
        if not recent:
            logger.debug("[QuestionExtractor] No segments in lookback window (cutoff=%.1f, now=%.1f, window=%.1f)", 
                        cutoff, now, self._config.lookback_window_s)
            return self.current_question
        logger.debug("[QuestionExtractor] Found %d segments in lookback window (last segment: %.1fs)", 
                     len(recent), recent[-1].end_time if recent else 0)

        # Split into sentences with timing info
        scored = self._score_sentences(recent)
        if not scored:
            logger.debug("[QuestionExtractor] No scored sentences found after processing segments")
            return self.current_question
        logger.debug("[QuestionExtractor] Scored %d sentences", len(scored))

        # Add ALL qualifying questions to history (not just the best)
        current_time = time.monotonic()
        for text, score in scored:
            norm = text.strip().lower()
            if norm not in self._seen_questions:
                self._seen_questions.add(norm)
                self._question_history.append({
                    "text": text,
                    "score": round(score, 2),
                    "time": current_time,
                })
                logger.info("[QuestionExtractor] New question detected: %s (score=%.2f)", text, score)

        # Pick the best question for auto-detection
        # (Staleness filtering happens in question_history property)
        best_text, best_score = max(scored, key=lambda x: x[1])
        logger.debug("[QuestionExtractor] Best question: '%s' (score=%.2f, min_confidence=%.2f)", 
                    best_text, best_score, self._config.min_confidence)

        if best_score < self._config.min_confidence:
            logger.debug("[QuestionExtractor] Best score %.2f below min_confidence %.2f, keeping current question", 
                        best_score, self._config.min_confidence)
            return self.current_question

        self._candidate_question = best_text

        # Debounce: don't change question too frequently
        if best_text != self._current_question:
            elapsed = time.monotonic() - self._last_change_time
            if elapsed < self._config.debounce_interval_s:
                logger.debug("[QuestionExtractor] Debouncing: %.2fs since last change (min=%.2fs), keeping current", 
                            elapsed, self._config.debounce_interval_s)
                return self.current_question

            self._current_question = best_text
            self._last_change_time = time.monotonic()
            logger.info("[QuestionExtractor] Active question changed to: %s (score=%.2f)", best_text, best_score)
        else:
            logger.debug("[QuestionExtractor] Best question unchanged: %s", best_text)

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
            logger.debug("[QuestionExtractor] No sentences extracted from segments")
            return []

        logger.debug("[QuestionExtractor] Extracted %d sentences from %d segments", len(sentences), total)

        scored: list[tuple[str, float]] = []
        for text, position in sentences:
            base_score = self._score_sentence(text)
            if base_score <= 0:
                logger.debug("[QuestionExtractor] Sentence scored 0: '%s'", text[:50])
                continue
            # Apply recency bias: sentences later in the window score higher
            score = base_score * (0.5 + 0.5 * position)
            scored.append((text, score))
            logger.debug("[QuestionExtractor] Sentence scored %.2f (base=%.2f, position=%.2f): '%s'", 
                        score, base_score, position, text[:50])

        logger.debug("[QuestionExtractor] %d sentences scored above 0 (out of %d)", len(scored), len(sentences))
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
