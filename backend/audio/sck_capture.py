from __future__ import annotations

import logging
import os
import queue
import signal
import subprocess
import threading

import numpy as np

from backend.config import AudioConfig

logger = logging.getLogger(__name__)

# The Swift helper outputs 16kHz mono Int16.
# 1600 samples * 2 bytes/sample = 3200 bytes per 100ms frame.
_FRAME_BYTES = 3200
_INT16_MAX = 32768.0


class SCKCapture:
    """Captures system audio via a ScreenCaptureKit subprocess.

    Spawns the AudioCapture Swift binary, reads raw PCM Int16 frames
    from its stdout, converts to float32, and provides them via a queue.

    Drop-in replacement for AudioCapture — same start/stop/read_frame API.
    """

    def __init__(self, config: AudioConfig, binary_path: str):
        self.config = config
        self.binary_path = binary_path
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=config.queue_maxsize)
        self._process: subprocess.Popen | None = None
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._overflow_count = 0

    def _read_exact(self, pipe, n: int) -> bytes | None:
        """Read exactly n bytes from pipe, or return None on EOF."""
        buf = bytearray()
        while len(buf) < n:
            chunk = pipe.read(n - len(buf))
            if not chunk:
                return None
            buf.extend(chunk)
        return bytes(buf)

    def _reader_loop(self) -> None:
        """Read PCM frames from subprocess stdout and enqueue as float32."""
        assert self._process is not None
        pipe = self._process.stdout
        assert pipe is not None

        while not self._stop_event.is_set():
            data = self._read_exact(pipe, _FRAME_BYTES)
            if data is None:
                if not self._stop_event.is_set():
                    logger.warning("AudioCapture subprocess ended unexpectedly")
                break

            # Convert Int16 little-endian to float32 in [-1.0, 1.0)
            samples = np.frombuffer(data, dtype="<i2").astype(np.float32) / _INT16_MAX

            try:
                self._queue.put_nowait(samples)
            except queue.Full:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self._queue.put_nowait(samples)
                except queue.Full:
                    pass
                self._overflow_count += 1
                if self._overflow_count % 100 == 1:
                    logger.warning(
                        "Audio queue overflow (count: %d), dropping frames",
                        self._overflow_count,
                    )

        logger.debug("Reader thread exiting")

    def _log_stderr(self) -> None:
        """Forward subprocess stderr to Python logging."""
        assert self._process is not None
        pipe = self._process.stderr
        assert pipe is not None
        for line in iter(pipe.readline, b""):
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                logger.debug("[AudioCapture] %s", text)

    def start(self) -> None:
        """Start the AudioCapture subprocess and reader thread."""
        if not os.path.isfile(self.binary_path):
            raise FileNotFoundError(
                f"AudioCapture binary not found at {self.binary_path}. "
                "Build it with: cd audio-capture && swift build -c release"
            )

        logger.info("Starting SCK audio capture: %s", self.binary_path)
        self._stop_event.clear()

        self._process = subprocess.Popen(
            [self.binary_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )

        self._stderr_thread = threading.Thread(
            target=self._log_stderr, daemon=True, name="sck-stderr",
        )
        self._stderr_thread.start()

        self._reader_thread = threading.Thread(
            target=self._reader_loop, daemon=True, name="sck-reader",
        )
        self._reader_thread.start()

        logger.info("SCK audio capture started (pid=%d)", self._process.pid)

    def stop(self) -> None:
        """Stop the subprocess and reader thread."""
        self._stop_event.set()

        if self._process is not None:
            try:
                self._process.send_signal(signal.SIGTERM)
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                logger.warning("AudioCapture did not exit in time, killing")
                self._process.kill()
                self._process.wait()
            except OSError:
                pass  # Process already exited
            self._process = None

        if self._reader_thread is not None:
            self._reader_thread.join(timeout=2)
            self._reader_thread = None

        logger.info("SCK audio capture stopped")

    def read_frame(self, timeout: float = 1.0) -> np.ndarray | None:
        """Read one mono float32 frame from the queue.

        Returns None on timeout.
        """
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None
