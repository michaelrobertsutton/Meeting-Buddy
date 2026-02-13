from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass

from backend.config import TranscriptConfig


@dataclass
class TranscriptSegment:
    text: str
    start_time: float
    end_time: float
    timestamp: float  # wall-clock time when segment was added

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "start_time": round(self.start_time, 2),
            "end_time": round(self.end_time, 2),
        }


class TranscriptBuffer:
    """Thread-safe rolling buffer of transcript segments."""

    def __init__(self, config: TranscriptConfig):
        self.config = config
        self._segments: deque[TranscriptSegment] = deque()
        self._lock = threading.Lock()
        self._version = 0

    def add_segment(self, text: str, start_time: float, end_time: float) -> None:
        """Add a new transcript segment and prune old ones."""
        segment = TranscriptSegment(
            text=text,
            start_time=start_time,
            end_time=end_time,
            timestamp=time.monotonic(),
        )
        with self._lock:
            self._segments.append(segment)
            self._prune()
            self._version += 1

    def _prune(self) -> None:
        """Remove segments older than max_age_s."""
        cutoff = time.monotonic() - self.config.max_age_s
        while self._segments and self._segments[0].timestamp < cutoff:
            self._segments.popleft()

    def get_segments(self) -> list[TranscriptSegment]:
        """Return a copy of current segments."""
        with self._lock:
            self._prune()
            return list(self._segments)

    def get_full_text(self) -> str:
        """Return concatenated text of all segments."""
        segments = self.get_segments()
        return " ".join(seg.text for seg in segments)

    def get_version(self) -> int:
        """Return the current version counter (incremented on each add)."""
        with self._lock:
            return self._version
