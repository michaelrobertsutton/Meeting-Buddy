"""Unit tests for SynthesisEngine LRU cache behaviour (Issue #316)."""
from __future__ import annotations

import sys
import types

import pytest

# Stub optional deps that may be absent in CI.
if "aiohttp" not in sys.modules:
    sys.modules["aiohttp"] = types.ModuleType("aiohttp")

if "openai" not in sys.modules:
    openai_mod = types.ModuleType("openai")

    class _AsyncOpenAI:  # pragma: no cover
        def __init__(self, api_key: str):
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=None))

    openai_mod.AsyncOpenAI = _AsyncOpenAI
    sys.modules["openai"] = openai_mod

from backend.config import SynthesisConfig
from backend.synthesis.engine import SynthesisEngine, SynthesisResult


def _engine(cache_max: int = 5) -> SynthesisEngine:
    cfg = SynthesisConfig(enabled=True, cache_max=cache_max)
    return SynthesisEngine(cfg, retriever=None)


def _result(label: str = "r") -> SynthesisResult:
    return SynthesisResult(one_liner=label, bullets=[label])


# ---------------------------------------------------------------------------
# cache_result round-trip
# ---------------------------------------------------------------------------

def test_cache_result_round_trip():
    """cache_result() inserts; a subsequent lookup returns the same result."""
    eng = _engine()
    r = _result("hello")
    eng.cache_result("What is X?", r)
    key = eng._cache_key("What is X?")
    assert eng._cache_get(key) is r


# ---------------------------------------------------------------------------
# Eviction at max capacity
# ---------------------------------------------------------------------------

def test_eviction_at_max_cache_size():
    """Inserting N+1 entries evicts the least-recently-used entry."""
    max_size = 3
    eng = _engine(cache_max=max_size)

    for i in range(max_size):
        eng.cache_result(f"q{i}", _result(f"r{i}"))

    # Cache is full; q0 is the LRU entry.
    assert len(eng._result_cache) == max_size

    # Insert one more — q0 should be evicted.
    eng.cache_result("q_new", _result("r_new"))
    assert len(eng._result_cache) == max_size
    assert eng._cache_get(eng._cache_key("q0")) is None
    assert eng._cache_get(eng._cache_key("q_new")) is not None


# ---------------------------------------------------------------------------
# LRU ordering — hit promotes entry
# ---------------------------------------------------------------------------

def test_lru_hit_promotes_entry():
    """A cache hit on an older entry keeps it alive when a newer entry arrives."""
    eng = _engine(cache_max=2)

    eng.cache_result("q_old", _result("r_old"))
    eng.cache_result("q_mid", _result("r_mid"))

    # Touch q_old — it should now be the MRU entry.
    key_old = eng._cache_key("q_old")
    eng._cache_get(key_old)

    # Insert a new entry; q_mid (now LRU) should be evicted, not q_old.
    eng.cache_result("q_new", _result("r_new"))
    assert eng._cache_get(eng._cache_key("q_mid")) is None
    assert eng._cache_get(eng._cache_key("q_old")) is not None


# ---------------------------------------------------------------------------
# Per-project cache key isolation
# ---------------------------------------------------------------------------

def test_per_project_cache_key_isolation():
    """Same question under different project slugs produces different cache keys."""
    eng = _engine()

    eng._project_slug = "project-a"
    eng.cache_result("budget?", _result("a-answer"))

    eng._project_slug = "project-b"
    eng.cache_result("budget?", _result("b-answer"))

    eng._project_slug = "project-a"
    key_a = eng._cache_key("budget?")
    eng._project_slug = "project-b"
    key_b = eng._cache_key("budget?")

    assert key_a != key_b

    eng._project_slug = "project-a"
    r_a = eng._cache_get(key_a)
    eng._project_slug = "project-b"
    r_b = eng._cache_get(key_b)

    assert r_a is not None and r_a.one_liner == "a-answer"
    assert r_b is not None and r_b.one_liner == "b-answer"


# ---------------------------------------------------------------------------
# Question normalisation
# ---------------------------------------------------------------------------

def test_question_normalisation():
    """Questions that differ only by whitespace/case share the same cache key."""
    eng = _engine()
    eng.cache_result("  What is X?  ", _result("norm"))

    key1 = eng._cache_key("  What is X?  ")
    key2 = eng._cache_key("what  is  x?")
    # Both normalised forms collapse whitespace and lowercase — should be equal.
    assert key1 == key2

    assert eng._cache_get(key1) is not None
