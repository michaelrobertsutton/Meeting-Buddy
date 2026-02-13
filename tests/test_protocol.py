import json

from backend.server.websocket import TranscriptWebSocket


class _DummyBuffer:
    def get_segments(self):
        return []

    def get_version(self):
        return 0


def test_build_message_includes_protocol_version():
    dummy = type("Dummy", (), {})()
    dummy.buffer = _DummyBuffer()
    dummy._extractor = None
    dummy._synthesis_in_flight = False
    dummy._active_answer = None
    dummy._qa_history = []
    dummy._pinned_answers = []

    msg = TranscriptWebSocket._build_message(dummy, "snapshot")
    assert msg["protocol_version"] == 1


def test_response_envelope_shape():
    # Simulate what _send_response produces
    resp = {"type": "response", "id": "1", "success": True, "data": {"ok": True}}
    raw = json.dumps(resp)
    out = json.loads(raw)
    assert out["type"] == "response"
    assert out["id"] == "1"
    assert out["success"] is True
    assert isinstance(out.get("data"), dict)
