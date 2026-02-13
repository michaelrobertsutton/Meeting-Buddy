from __future__ import annotations

import logging
import queue

import numpy as np
import sounddevice as sd
from scipy.signal import resample_poly
from math import gcd

from backend.config import AudioConfig

logger = logging.getLogger(__name__)


class AudioCapture:
    """Captures audio from a device and provides resampled mono 16kHz frames via a queue."""

    def __init__(self, config: AudioConfig, device_index: int):
        self.config = config
        self.device_index = device_index
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=config.queue_maxsize)
        self._stream: sd.InputStream | None = None
        self._overflow_count = 0

        # Precompute resampling factors
        g = gcd(config.sample_rate, config.target_sample_rate)
        self._resample_up = config.target_sample_rate // g
        self._resample_down = config.sample_rate // g

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if status:
            logger.warning("Audio callback status: %s", status)

        # Mix to mono: average across channels
        if indata.shape[1] > 1:
            mono = indata.mean(axis=1)
        else:
            mono = indata[:, 0]

        # Resample from native rate to 16kHz
        if self.config.sample_rate != self.config.target_sample_rate:
            mono = resample_poly(mono, self._resample_up, self._resample_down).astype(np.float32)

        try:
            self._queue.put_nowait(mono)
        except queue.Full:
            # Drop oldest frame to maintain live latency
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(mono)
            except queue.Full:
                pass
            self._overflow_count += 1
            if self._overflow_count % 100 == 1:
                logger.warning("Audio queue overflow (count: %d), dropping frames", self._overflow_count)

    def start(self) -> None:
        """Start capturing audio."""
        logger.info(
            "Starting audio capture: device=%d, rate=%dHz, block=%d samples",
            self.device_index, self.config.sample_rate, self.config.block_size,
        )
        self._stream = sd.InputStream(
            device=self.device_index,
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            blocksize=self.config.block_size,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        """Stop capturing audio."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
            logger.info("Audio capture stopped")

    def read_frame(self, timeout: float = 1.0) -> np.ndarray | None:
        """Read one resampled mono frame from the queue.

        Returns None on timeout.
        """
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None
