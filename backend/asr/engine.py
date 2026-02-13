import logging

import numpy as np
from faster_whisper import WhisperModel

from backend.config import ASRConfig

logger = logging.getLogger(__name__)


class ASREngine:
    """Whisper-based speech recognition engine using faster-whisper."""

    def __init__(self, config: ASRConfig):
        self.config = config
        logger.info(
            "Loading Whisper model: %s (device=%s, compute=%s)",
            config.model_size, config.device, config.compute_type,
        )
        self.model = WhisperModel(
            config.model_size,
            device=config.device,
            compute_type=config.compute_type,
        )
        logger.info("Whisper model loaded")

    def transcribe_chunk(self, audio: np.ndarray) -> list[dict]:
        """Transcribe an audio chunk.

        Args:
            audio: mono float32 audio at 16kHz

        Returns:
            List of segment dicts with keys: text, start, end, no_speech_prob
        """
        segments, info = self.model.transcribe(
            audio,
            beam_size=self.config.beam_size,
            language=self.config.language,
            condition_on_previous_text=False,
            vad_filter=False,
        )

        results = []
        for seg in segments:
            results.append({
                "text": seg.text.strip(),
                "start": seg.start,
                "end": seg.end,
                "no_speech_prob": seg.no_speech_prob,
            })
        return results
