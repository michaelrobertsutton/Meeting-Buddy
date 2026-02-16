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
        self._diag_lock = threading.Lock()
        self._overflow_count = 0
        self._frames_received = 0
        self._last_frame_time: float | None = None
        self._process_exit_code: int | None = None
        self._stderr_lines: list[str] = []

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
        import time
        
        assert self._process is not None
        pipe = self._process.stdout
        assert pipe is not None

        logger.info("AudioCapture reader thread started")
        first_frame_logged = False

        while not self._stop_event.is_set():
            data = self._read_exact(pipe, _FRAME_BYTES)
            if data is None:
                if not self._stop_event.is_set():
                    # Check if process exited
                    exit_code = self._process.poll()
                    if exit_code is not None:
                        with self._diag_lock:
                            self._process_exit_code = exit_code
                        logger.error(
                            "AudioCapture subprocess ended unexpectedly with exit code %d",
                            exit_code
                        )
                        if self._stderr_lines:
                            logger.error("AudioCapture stderr output:\n%s", "\n".join(self._stderr_lines[-10:]))
                    else:
                        logger.warning("AudioCapture subprocess stdout closed unexpectedly")
                break

            # Convert Int16 little-endian to float32 in [-1.0, 1.0)
            samples = np.frombuffer(data, dtype="<i2").astype(np.float32) / _INT16_MAX
            
            # Check if audio is actually present (not just silence)
            audio_level = np.abs(samples).max()
            if audio_level > 0.001:  # Non-silent audio detected
                if not first_frame_logged:
                    logger.info("Audio frames received (level: %.3f)", audio_level)
                    first_frame_logged = True

            with self._diag_lock:
                self._frames_received += 1
                self._last_frame_time = time.time()

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
                with self._diag_lock:
                    self._overflow_count += 1
                if self._overflow_count % 100 == 1:
                    logger.warning(
                        "Audio queue overflow (count: %d), dropping frames",
                        self._overflow_count,
                    )

        logger.info("Reader thread exiting (received %d frames total)", self._frames_received)

    def _log_stderr(self) -> None:
        """Forward subprocess stderr to Python logging."""
        assert self._process is not None
        pipe = self._process.stderr
        assert pipe is not None
        for line in iter(pipe.readline, b""):
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                self._stderr_lines.append(text)
                # Log errors and warnings at appropriate levels
                if "ERROR" in text.upper() or "FAILED" in text.upper():
                    logger.error("[AudioCapture] %s", text)
                elif "WARNING" in text.upper() or "WARN" in text.upper():
                    logger.warning("[AudioCapture] %s", text)
                else:
                    logger.info("[AudioCapture] %s", text)

    def start(self) -> None:
        """Start the AudioCapture subprocess and reader thread."""
        import time
        
        if not os.path.isfile(self.binary_path):
            raise FileNotFoundError(
                f"AudioCapture binary not found at {self.binary_path}. "
                "Build it with: cd audio-capture && swift build -c release"
            )

        logger.info("Starting SCK audio capture: %s", self.binary_path)
        self._stop_event.clear()
        self._frames_received = 0
        self._last_frame_time = None
        self._process_exit_code = None
        self._stderr_lines = []

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
        
        # Give it a moment to start, then check if process is still alive
        time.sleep(0.5)
        if self._process.poll() is not None:
            exit_code = self._process.returncode
            logger.error(
                "AudioCapture process exited immediately with code %d. "
                "Check Screen Recording permission in System Settings.",
                exit_code
            )
            if self._stderr_lines:
                logger.error("AudioCapture error output:\n%s", "\n".join(self._stderr_lines))

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
    
    def get_status(self) -> dict:
        """Return diagnostic status information."""
        import time

        with self._diag_lock:
            frames_received = self._frames_received
            overflow_count = self._overflow_count
            last_frame_time = self._last_frame_time

        status = {
            "running": self._process is not None and self._process.poll() is None,
            "frames_received": frames_received,
            "queue_size": self._queue.qsize(),
            "overflow_count": overflow_count,
        }

        if self._process:
            status["pid"] = self._process.pid
            status["exit_code"] = self._process.poll()

        if last_frame_time is not None:
            time_since_last_frame = time.time() - last_frame_time
            status["seconds_since_last_frame"] = time_since_last_frame
            status["receiving_audio"] = time_since_last_frame < 2.0
        else:
            status["receiving_audio"] = False

        if self._stderr_lines:
            status["last_stderr_lines"] = self._stderr_lines[-5:]

        return status
