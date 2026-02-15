import io
import threading

import numpy as np

from backend.audio.sck_capture import SCKCapture
from backend.config import AudioConfig


from typing import Optional


class _FakeProcess:
    def __init__(self, stdout_bytes: bytes, exit_code: Optional[int] = 0, pid: int = 123):
        self.stdout = io.BytesIO(stdout_bytes)
        self.stderr = io.BytesIO(b"")
        self._exit_code = exit_code
        self.pid = pid

    def poll(self):
        # Simulate that once stdout is exhausted, the process has exited.
        at_end = self.stdout.tell() >= len(self.stdout.getvalue())
        return self._exit_code if at_end else None


def _int16_frame(samples: int = 1600, value: int = 1000) -> bytes:
    arr = (np.ones(samples, dtype=np.int16) * value).astype("<i2")
    return arr.tobytes()


def test_reader_loop_parses_frames_and_handles_eof():
    cfg = AudioConfig(queue_maxsize=10)
    cap = SCKCapture(cfg, binary_path="/dev/null")

    # Two frames then EOF.
    payload = _int16_frame() + _int16_frame(value=2000)
    cap._process = _FakeProcess(payload, exit_code=0)
    cap._stop_event.clear()

    t = threading.Thread(target=cap._reader_loop)
    t.start()
    t.join(timeout=2)

    f1 = cap.read_frame(timeout=0.1)
    f2 = cap.read_frame(timeout=0.1)
    f3 = cap.read_frame(timeout=0.1)

    assert f1 is not None and f2 is not None
    assert f3 is None

    assert f1.dtype == np.float32
    assert f1.shape == (cfg.target_block_size,)
    assert np.isclose(float(np.max(np.abs(f1))), 1000 / 32768.0, atol=1e-6)
    assert np.isclose(float(np.max(np.abs(f2))), 2000 / 32768.0, atol=1e-6)


def test_reader_loop_drops_frames_on_queue_overflow():
    cfg = AudioConfig(queue_maxsize=1)
    cap = SCKCapture(cfg, binary_path="/dev/null")

    # 3 frames with max queue size 1 should overflow at least once.
    payload = _int16_frame() + _int16_frame() + _int16_frame()
    cap._process = _FakeProcess(payload, exit_code=0)
    cap._stop_event.clear()

    t = threading.Thread(target=cap._reader_loop)
    t.start()
    t.join(timeout=2)

    # Only one frame should remain available.
    f1 = cap.read_frame(timeout=0.1)
    f2 = cap.read_frame(timeout=0.1)
    assert f1 is not None
    assert f2 is None

    status = cap.get_status()
    assert status["overflow_count"] >= 1
