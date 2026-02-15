import sys
import threading
import time
import types

import numpy as np

# Stub modules so importing backend.asr.* works in minimal dev env (no torch/whisper).
if "faster_whisper" not in sys.modules:
    fw = types.ModuleType("faster_whisper")

    class _WhisperModel:  # pragma: no cover
        def __init__(self, *args, **kwargs):
            pass

    fw.WhisperModel = _WhisperModel
    sys.modules["faster_whisper"] = fw

# Avoid importing torch/silero by stubbing backend.asr.vad (StreamingASR only needs .reset())
if "backend.asr.vad" not in sys.modules:
    vad_mod = types.ModuleType("backend.asr.vad")

    class _VADFilter:  # pragma: no cover
        def __init__(self, *args, **kwargs):
            raise RuntimeError("VADFilter stub should not be instantiated in unit tests")

    vad_mod.VADFilter = _VADFilter
    sys.modules["backend.asr.vad"] = vad_mod

from backend.asr.streaming import StreamingASR
from backend.config import AudioConfig, StreamingConfig


class _FakeCapture:
    def __init__(self, frames):
        self._frames = list(frames)
        self._lock = threading.Lock()

    def start(self):
        pass

    def stop(self):
        pass

    def read_frame(self, timeout: float = 1.0):
        # Return next frame, then None.
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if self._frames:
                    return self._frames.pop(0)
            time.sleep(0.01)
        return None


class _FakeVAD:
    def __init__(self, speech_mask):
        self._mask = list(speech_mask)
        self.reset_called = 0

    def is_speech(self, frame: np.ndarray) -> bool:
        if not self._mask:
            return False
        return self._mask.pop(0)

    def reset(self) -> None:
        self.reset_called += 1


class _FakeEngine:
    def __init__(self):
        self.calls = []
        self.config = type("cfg", (), {"no_speech_threshold": 1.0})()

    def transcribe_chunk(self, audio: np.ndarray):
        self.calls.append(len(audio))
        return [{"text": "hello", "start": 0.0, "end": 0.1, "no_speech_prob": 0.0}]


def test_streaming_asr_end_to_end_mock_audio_to_callback():
    audio_cfg = AudioConfig(block_duration_ms=100)
    streaming_cfg = StreamingConfig(
        pre_speech_buffer_ms=0,
        silence_duration_ms=200,  # 2 frames of silence ends speech
        min_chunk_duration_s=0.0,
        max_chunk_duration_s=5.0,
    )

    # 3 speech frames, then 2 silent frames.
    frames = [np.ones(audio_cfg.target_block_size, dtype=np.float32) * 0.1] * 5
    vad = _FakeVAD([True, True, True, False, False])
    cap = _FakeCapture(frames)
    eng = _FakeEngine()

    out = []

    def on_final(text: str, start_s: float, end_s: float):
        out.append((text, start_s, end_s))

    asr = StreamingASR(
        capture=cap,
        vad=vad,
        engine=eng,
        audio_config=audio_cfg,
        streaming_config=streaming_cfg,
        on_final=on_final,
    )

    asr.start()

    # Wait for callback (best-effort; should be quick)
    deadline = time.time() + 2.0
    while time.time() < deadline and not out:
        time.sleep(0.02)

    asr.stop()

    assert out, "Expected at least one finalized transcript"
    assert out[0][0] == "hello"
    assert eng.calls, "Engine should have been invoked"
