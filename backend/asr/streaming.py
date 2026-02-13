from __future__ import annotations

import enum
import logging
import threading
import time
from collections import deque
from typing import Callable

import numpy as np

from backend.audio.capture import AudioCapture
from backend.asr.engine import ASREngine
from backend.asr.vad import VADFilter
from backend.config import AudioConfig, StreamingConfig

logger = logging.getLogger(__name__)


class _State(enum.Enum):
    IDLE = "idle"
    ACCUMULATING = "accumulating"


class StreamingASR:
    """Orchestrates audio capture → VAD → ASR in a background thread.

    State machine:
        IDLE: Run VAD on each frame. Maintain a pre-speech ring buffer.
        ACCUMULATING: Buffer speech frames until silence or max duration.
        On trigger: concatenate, transcribe, invoke callback.
    """

    def __init__(
        self,
        capture: AudioCapture,
        vad: VADFilter,
        engine: ASREngine,
        audio_config: AudioConfig,
        streaming_config: StreamingConfig,
        on_final: Callable[[str, float, float], None] | None = None,
    ):
        self.capture = capture
        self.vad = vad
        self.engine = engine
        self.audio_config = audio_config
        self.config = streaming_config
        self.on_final = on_final

        self._state = _State.IDLE
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        # Pre-speech ring buffer (keeps last N frames before speech detected)
        pre_speech_frames = max(1, int(
            self.config.pre_speech_buffer_ms / self.audio_config.block_duration_ms
        ))
        self._pre_speech_buffer: deque[np.ndarray] = deque(maxlen=pre_speech_frames)

        # Accumulation buffer for current speech chunk
        self._speech_frames: list[np.ndarray] = []
        self._speech_start_time: float = 0.0
        self._silence_frames: int = 0

        # How many consecutive silent frames trigger end-of-speech
        self._silence_threshold = max(1, int(
            self.config.silence_duration_ms / self.audio_config.block_duration_ms
        ))

        # Max frames before forced transcription
        self._max_speech_frames = max(1, int(
            self.config.max_chunk_duration_s * 1000 / self.audio_config.block_duration_ms
        ))

        # Track wall-clock time for segment timestamps
        self._start_wall_time: float = 0.0

    def start(self) -> None:
        """Start the streaming ASR background thread."""
        self._stop_event.clear()
        self._start_wall_time = time.monotonic()
        self._thread = threading.Thread(target=self._loop, name="streaming-asr", daemon=True)
        self._thread.start()
        logger.info("Streaming ASR started")

    def stop(self) -> None:
        """Stop the streaming ASR thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        logger.info("Streaming ASR stopped")

    def _elapsed(self) -> float:
        """Seconds since start."""
        return time.monotonic() - self._start_wall_time

    def _loop(self) -> None:
        """Main processing loop (runs in background thread)."""
        while not self._stop_event.is_set():
            frame = self.capture.read_frame(timeout=0.5)
            if frame is None:
                continue

            if self._state == _State.IDLE:
                self._handle_idle(frame)
            elif self._state == _State.ACCUMULATING:
                self._handle_accumulating(frame)

    def _handle_idle(self, frame: np.ndarray) -> None:
        """In IDLE state: run VAD, buffer pre-speech audio."""
        self._pre_speech_buffer.append(frame)

        if self.vad.is_speech(frame):
            # Transition to ACCUMULATING
            self._state = _State.ACCUMULATING
            self._speech_start_time = self._elapsed()
            self._silence_frames = 0

            # Include pre-speech buffer to avoid clipping word starts
            self._speech_frames = list(self._pre_speech_buffer)
            self._pre_speech_buffer.clear()

            logger.debug("Speech detected at %.1fs", self._speech_start_time)

    def _handle_accumulating(self, frame: np.ndarray) -> None:
        """In ACCUMULATING state: buffer speech, detect end-of-speech or max duration."""
        self._speech_frames.append(frame)

        if self.vad.is_speech(frame):
            self._silence_frames = 0
        else:
            self._silence_frames += 1

        # Check if we should trigger transcription
        hit_silence = self._silence_frames >= self._silence_threshold
        hit_max_duration = len(self._speech_frames) >= self._max_speech_frames

        if hit_silence or hit_max_duration:
            self._trigger_transcription()

    def _trigger_transcription(self) -> None:
        """Concatenate buffered frames, run ASR, invoke callback."""
        end_time = self._elapsed()

        # Concatenate all frames into a single audio array
        audio = np.concatenate(self._speech_frames)

        # Check minimum duration
        duration_s = len(audio) / self.audio_config.target_sample_rate
        if duration_s < self.config.min_chunk_duration_s:
            logger.debug("Skipping short chunk (%.2fs)", duration_s)
            self._reset_to_idle()
            return

        logger.debug(
            "Transcribing %.2fs of audio (%.1fs - %.1fs)",
            duration_s, self._speech_start_time, end_time,
        )

        # Run ASR
        segments = self.engine.transcribe_chunk(audio)

        for seg in segments:
            if seg["no_speech_prob"] > self.engine.config.no_speech_threshold:
                logger.debug("Skipping high no_speech_prob segment: %.2f", seg["no_speech_prob"])
                continue

            text = seg["text"]
            if not text:
                continue

            if self.on_final:
                self.on_final(text, self._speech_start_time, end_time)

        self._reset_to_idle()

    def _reset_to_idle(self) -> None:
        """Reset state back to IDLE."""
        self._state = _State.IDLE
        self._speech_frames.clear()
        self._silence_frames = 0
        self.vad.reset()
