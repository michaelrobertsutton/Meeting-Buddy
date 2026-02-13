from __future__ import annotations

import logging

import sounddevice as sd

logger = logging.getLogger(__name__)


def list_audio_devices() -> list[dict]:
    """List all available audio input devices."""
    devices = sd.query_devices()
    inputs = []
    for i, dev in enumerate(devices):
        if dev["max_input_channels"] > 0:
            inputs.append({
                "index": i,
                "name": dev["name"],
                "channels": dev["max_input_channels"],
                "sample_rate": dev["default_samplerate"],
            })
    return inputs


def find_blackhole_device(name_hint: str = "BlackHole") -> dict | None:
    """Find a BlackHole audio device by name substring.

    Returns device info dict with index, name, channels, sample_rate,
    or None if not found.
    """
    devices = list_audio_devices()
    for dev in devices:
        if name_hint.lower() in dev["name"].lower():
            logger.info("Found BlackHole device: %s (index %d)", dev["name"], dev["index"])
            return dev
    logger.warning("No device matching '%s' found", name_hint)
    return None


def print_devices() -> None:
    """Print all input devices to stdout for diagnostics."""
    devices = list_audio_devices()
    if not devices:
        print("No input devices found!")
        return
    print(f"{'Index':<8} {'Name':<40} {'Channels':<10} {'Sample Rate':<12}")
    print("-" * 70)
    for dev in devices:
        print(f"{dev['index']:<8} {dev['name']:<40} {dev['channels']:<10} {dev['sample_rate']:<12.0f}")
