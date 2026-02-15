from __future__ import annotations

import logging

import numpy as np

from backend.config import VADConfig

logger = logging.getLogger(__name__)

# Silero VAD v5 supported window sizes at 16kHz
_SUPPORTED_WINDOW_SIZES_16K = [512, 1024, 1536]


class VADFilter:
    """Voice Activity Detection using Silero VAD.

    Silero VAD requires specific window sizes (512, 1024, or 1536 samples at 16kHz).
    This wrapper handles arbitrary frame sizes by chunking into supported windows.

    ``torch`` and ``silero_vad`` are imported lazily inside ``__init__`` so that
    tests and lightweight code can import this module without the full ML stack
    installed.
    """

    def __init__(self, config: VADConfig, sample_rate: int = 16000):
        # Lazy imports — keep module importable without torch/silero_vad installed.
        try:
            import torch  # noqa: PLC0415
            from silero_vad import load_silero_vad  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "torch and silero-vad are required for VAD. "
                "Install them with: pip install torch silero-vad"
            ) from exc

        self._torch = torch
        self.config = config
        self.sample_rate = sample_rate
        self._window_size = 512  # Smallest supported window for lowest latency
        logger.info("Loading Silero VAD (onnx=%s)", config.use_onnx)
        self.model = load_silero_vad(onnx=config.use_onnx)

    def is_speech(self, frame: np.ndarray) -> bool:
        """Check if an audio frame contains speech.

        Processes the frame in 512-sample windows. Returns True if any
        window exceeds the speech threshold.

        Args:
            frame: mono float32 audio at 16kHz
        """
        for start in range(0, len(frame) - self._window_size + 1, self._window_size):
            chunk = frame[start:start + self._window_size]
            tensor = self._torch.from_numpy(chunk)
            prob = self.model(tensor, self.sample_rate).item()
            if prob >= self.config.threshold:
                return True
        return False

    def reset(self) -> None:
        """Reset model state between utterances."""
        self.model.reset_states()
