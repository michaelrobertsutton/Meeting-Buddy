import asyncio

from backend.server.websocket import TranscriptWebSocket


def test_get_status_shape():
    dummy = type("Dummy", (), {})()
    dummy._settings_manager = None
    dummy._session_start = 0.0

    out = asyncio.run(TranscriptWebSocket._cmd_get_status(dummy, {}))

    assert out["protocol_version"] == 1
    assert "backend" in out
    assert "started_at" in out["backend"]
    assert "uptime_s" in out["backend"]
    assert "version" in out["backend"]
    assert isinstance(out.get("capabilities"), dict)
