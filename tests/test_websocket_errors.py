import asyncio
import json

from backend.config import ServerConfig, TranscriptConfig
from backend.server.websocket import TranscriptWebSocket
from backend.transcript.buffer import TranscriptBuffer


class _FakeWS:
    def __init__(self, incoming=None):
        self.sent = []
        self._incoming = list(incoming or [])

    async def send(self, data: str):
        self.sent.append(data)

    def __aiter__(self):
        async def _gen():
            for item in self._incoming:
                yield item
        return _gen()


def test_handle_command_unknown_command_returns_error():
    ws = _FakeWS()
    server = TranscriptWebSocket(ServerConfig(), TranscriptBuffer(TranscriptConfig(max_age_s=10.0)))

    asyncio.run(server._handle_command(ws, {"id": "1", "command": "nope", "params": {}}))

    assert len(ws.sent) == 1
    resp = json.loads(ws.sent[0])
    assert resp["type"] == "response"
    assert resp["id"] == "1"
    assert resp["success"] is False
    assert "Unknown command" in resp["error"]


def test_handler_ignores_malformed_json_messages():
    # Feed a malformed JSON line; handler should not throw.
    ws = _FakeWS(incoming=["{this is not json}"])
    server = TranscriptWebSocket(ServerConfig(), TranscriptBuffer(TranscriptConfig(max_age_s=10.0)))

    asyncio.run(server._handler(ws))

    # It should have sent a snapshot on connect.
    assert ws.sent
    snap = json.loads(ws.sent[0])
    assert snap["type"] == "snapshot"
