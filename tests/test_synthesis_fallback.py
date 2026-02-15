import asyncio
import sys
import types

import pytest

# The dev test environment may not have optional runtime deps installed.
# Provide minimal stubs so we can exercise fallback behavior without network calls.
if "aiohttp" not in sys.modules:
    sys.modules["aiohttp"] = types.ModuleType("aiohttp")

if "openai" not in sys.modules:
    openai = types.ModuleType("openai")

    class _AsyncOpenAI:  # pragma: no cover
        def __init__(self, api_key: str):
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=None))

    openai.AsyncOpenAI = _AsyncOpenAI
    sys.modules["openai"] = openai

from backend.config import SynthesisConfig
from backend.synthesis.engine import SynthesisEngine, SynthesisResult


def test_synthesis_uncached_returns_empty_result_on_exception(monkeypatch):
    cfg = SynthesisConfig(enabled=True)
    eng = SynthesisEngine(cfg, retriever=None)

    async def _boom(_prompt: str) -> str:
        raise RuntimeError("api down")

    monkeypatch.setattr(eng, "_call_openai_api", _boom)

    out = asyncio.run(eng.synthesize_once("what now"))
    assert isinstance(out, SynthesisResult)
    assert out.one_liner == ""
    assert out.bullets == []
    assert out.confidence == 0.0


def test_simple_json_call_uses_chatgpt_backend_in_oauth_mode(monkeypatch):
    cfg = SynthesisConfig(enabled=True)
    eng = SynthesisEngine(cfg, retriever=None)

    # Force OAuth mode (so _client is not used)
    eng._oauth_token = "tok"
    eng._chatgpt_account_id = "acct"

    async def _fake(system, user, max_tokens=0):
        return "{}"

    monkeypatch.setattr(eng, "_call_chatgpt_backend_custom", _fake)

    s = asyncio.run(eng.simple_json_call("sys", "user", max_tokens=10))
    assert s == "{}"
