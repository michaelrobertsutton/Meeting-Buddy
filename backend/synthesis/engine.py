from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections import OrderedDict
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

from backend.synthesis.prompt import SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)

# ChatGPT backend for OAuth (uses ChatGPT Plus/Pro subscription quota)
_CHATGPT_BACKEND_URL = "https://chatgpt.com/backend-api/codex/responses"
_CHATGPT_DEFAULT_MODEL = "gpt-5.2-codex"
_USER_AGENT = "codex_cli_rs/0.1.0 (meeting-buddy)"


@dataclass
class SynthesisResult:
    one_liner: str = ""
    bullets: list[str] = field(default_factory=list)
    process_bullets: list[str] = field(default_factory=list)
    best_practice_bullets: list[str] = field(default_factory=list)
    next_step: str = ""
    clarifiers: list[str] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    confidence: float = 0.0
    inferred: bool = False
    reasoning: str = ""

    def to_dict(self) -> dict:
        return {
            "one_liner": self.one_liner,
            "bullets": self.bullets,
            "process_bullets": self.process_bullets,
            "best_practice_bullets": self.best_practice_bullets,
            "next_step": self.next_step,
            "clarifiers": self.clarifiers,
            "citations": self.citations,
            "confidence": self.confidence,
            "inferred": self.inferred,
            "reasoning": self.reasoning,
        }


class SynthesisEngine:
    """Calls OpenAI to synthesize answers from retrieved chunks."""

    def __init__(self, config, retriever=None) -> None:
        from openai import AsyncOpenAI

        self._config = config
        self._retriever = retriever
        # Try env var first; fall back to placeholder (overridden by reinit_client*)
        import os
        api_key = os.environ.get("OPENAI_API_KEY", "placeholder")
        self._client = AsyncOpenAI(api_key=api_key)
        self._last_question: str | None = None
        self._last_result: SynthesisResult | None = None
        self._last_retrieval_ms: float | None = None
        # LRU cache
        self._project_slug: str | None = None
        self._result_cache: OrderedDict[str, SynthesisResult] = OrderedDict()
        self._cache_hit: bool = False
        # OAuth fields (set via reinit_client_oauth)
        self._oauth_token: str | None = None
        self._chatgpt_account_id: str | None = None

    def reinit_client(self, api_key: str) -> None:
        """Swap the OpenAI client with a new API key (standard platform billing)."""
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)
        self._oauth_token = None
        self._chatgpt_account_id = None
        self._last_question = None
        logger.info("Synthesis client reinitialized with API key")

    def reinit_client_oauth(self, access_token: str, chatgpt_account_id: str) -> None:
        """Configure for ChatGPT backend (uses Plus/Pro subscription quota)."""
        self._oauth_token = access_token
        self._chatgpt_account_id = chatgpt_account_id
        self._oauth_model = _CHATGPT_DEFAULT_MODEL
        self._client = None  # not used in OAuth mode
        self._last_question = None
        logger.info("Synthesis client reinitialized for ChatGPT backend (model=%s, account=%s)", _CHATGPT_DEFAULT_MODEL, chatgpt_account_id[:8] + "...")

    def set_retriever(self, retriever, project_slug=None):
        """Swap the retriever (e.g. after project switch). Clears the LRU cache."""
        self._retriever = retriever
        self._project_slug = project_slug
        self._last_question = None
        self._last_result = None
        self._last_retrieval_ms = None
        self._result_cache.clear()

    def _cache_key(self, question):
        norm = re.sub(r'\s+', ' ', question.strip().lower())
        return f"{self._project_slug or ''}|{norm}"

    def _cache_put(self, key, result):
        self._result_cache.pop(key, None)
        self._result_cache[key] = result
        while len(self._result_cache) > self._config.cache_max:
            self._result_cache.popitem(last=False)

    def _cache_get(self, key) -> SynthesisResult | None:
        """Get a cached result and move it to the end (LRU update)."""
        result = self._result_cache.pop(key, None)
        if result is not None:
            self._result_cache[key] = result  # re-insert at end = most recently used
        return result

    def cache_result(self, question, result, chunks=None):
        """Store a result in the LRU cache."""
        self._cache_put(self._cache_key(question), result)

    @property
    def cache_hit(self):
        """True if the last synthesize call was served from cache."""
        return self._cache_hit

    @property
    def last_retrieval_ms(self) -> float | None:
        """Retrieval latency in milliseconds from the most recent synthesis call."""
        return self._last_retrieval_ms

    async def synthesize(self, question, transcript_context=None):
        """Synthesize an answer for the given question. Returns None if unchanged."""
        key = self._cache_key(question)
        cached = self._cache_get(key)
        if cached is not None:
            self._cache_hit = True
            self._last_question = question
            self._last_result = cached
            logger.info("Cache hit (%d entries): %s", len(self._result_cache), question[:80])
            return self._last_result
        self._cache_hit = False
        if question == self._last_question:
            return None
        self._last_question = question
        result = await self._synthesize_uncached(question, transcript_context=transcript_context)
        self._last_result = result
        return result

    async def synthesize_stream(self, question, transcript_context=None, prefetched_chunks=None):
        """Synthesize with streaming. Yields partial text deltas."""
        key = self._cache_key(question)
        cached = self._cache_get(key)
        if cached is not None:
            self._cache_hit = True
            self._last_question = question
            self._last_result = cached
            logger.info("Cache hit (%d entries): %s", len(self._result_cache), question[:80])
            return  # no yields -> websocket fallback hits synthesize() -> returns cached result
        self._cache_hit = False
        if question == self._last_question:
            return
        self._last_question = question
        async for delta in self._synthesize_stream_uncached(
            question, transcript_context=transcript_context,
            prefetched_chunks=prefetched_chunks,
        ):
            yield delta

    async def synthesize_batch(self, questions: list[str]) -> dict[str, SynthesisResult]:
        """Synthesize a batch of questions (no last-question caching)."""
        out: dict[str, SynthesisResult] = {}
        for q in questions:
            qq = (q or "").strip()
            if not qq:
                continue
            out[qq] = await self.synthesize_once(qq)
        return out

    async def synthesize_once(self, question: str) -> SynthesisResult:
        """Synthesize without last-question caching (useful for prep mode)."""
        return await self._synthesize_uncached(question)

    async def simple_json_call(
        self,
        system_instructions: str,
        user_prompt: str,
        max_tokens: int = 800,
        temperature: float | None = None,
    ) -> str:
        """Run a lightweight JSON-only call (used for prep question generation, etc.)."""
        if self._oauth_token and self._chatgpt_account_id:
            return await self._call_chatgpt_backend_custom(
                system_instructions, user_prompt, max_tokens=max_tokens
            )
        return await self._call_openai_api_custom(
            system_instructions,
            user_prompt,
            max_tokens=max_tokens,
            temperature=temperature if temperature is not None else self._config.temperature,
        )

    async def _synthesize_uncached(self, question: str, transcript_context: str | None = None) -> SynthesisResult:
        # Retrieve context chunks
        results = []
        if self._retriever:
            loop = asyncio.get_event_loop()
            t_ret = time.monotonic()
            results = await loop.run_in_executor(
                None, self._retriever.retrieve, question
            )
            self._last_retrieval_ms = round((time.monotonic() - t_ret) * 1000.0, 1)
            logger.info("Retrieved %d chunks for synthesis (%.1f ms)", len(results), self._last_retrieval_ms)
        else:
            self._last_retrieval_ms = None

        doc_registry = None
        if self._retriever and hasattr(self._retriever, "get_doc_registry"):
            try:
                doc_registry = self._retriever.get_doc_registry()
            except (FileNotFoundError, OSError, json.JSONDecodeError):
                doc_registry = None
            except Exception as e:
                logger.warning("Failed to load doc registry for synthesis: %s", e)
                doc_registry = None

        user_prompt = build_user_prompt(
            question, results, doc_registry=doc_registry, transcript_context=transcript_context
        )

        try:
            if self._oauth_token and self._chatgpt_account_id:
                content = await self._call_chatgpt_backend(user_prompt)
            else:
                content = await self._call_openai_api(user_prompt)

            data = json.loads(content)

            result = SynthesisResult(
                one_liner=data.get("one_liner", ""),
                bullets=data.get("bullets", []),
                process_bullets=data.get("process_bullets", []),
                best_practice_bullets=data.get("best_practice_bullets", []),
                next_step=data.get("next_step", "") or "",
                clarifiers=data.get("clarifiers", []),
                citations=data.get("citations", []),
                confidence=float(data.get("confidence", 0.0)),
                inferred=bool(data.get("inferred", False)),
                reasoning=data.get("reasoning", "") or "",
            )

            # Validate citations
            if results:
                valid_titles = {r.doc_title for r in results}
                result.citations = [
                    c for c in result.citations
                    if c.get("doc") in valid_titles
                ]

            key = self._cache_key(question)
            self._cache_put(key, result)
            logger.info(
                "Synthesis complete: %d bullets, confidence=%.2f",
                len(result.bullets), result.confidence,
            )
            return result

        except Exception:
            logger.exception("Synthesis failed")
            return SynthesisResult(one_liner="", bullets=[], confidence=0.0)

    async def _call_openai_api(self, user_prompt: str) -> str:
        """Standard OpenAI API call (platform billing)."""
        return await self._call_openai_api_custom(
            SYSTEM_PROMPT,
            user_prompt,
            max_tokens=self._config.max_tokens,
            temperature=self._config.temperature,
        )

    async def _call_openai_api_custom(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        response = await self._client.chat.completions.create(
            model=self._config.model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content

    async def _call_chatgpt_backend(self, user_prompt: str) -> str:
        """ChatGPT backend call via SSE streaming (uses Plus/Pro subscription quota)."""
        return await self._call_chatgpt_backend_custom(
            SYSTEM_PROMPT,
            user_prompt,
            max_tokens=self._config.max_tokens,
        )

    async def _call_chatgpt_backend_custom(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
    ) -> str:
        headers = {
            "Authorization": f"Bearer {self._oauth_token}",
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
            "chatgpt-account-id": self._chatgpt_account_id,
            "originator": "codex_cli_rs",
        }
        # Codex backend only supports: model, instructions, input, stream, store
        payload = {
            "model": self._oauth_model,
            "instructions": system_prompt,
            "input": [
                {"role": "user", "content": user_prompt},
            ],
            "stream": True,
            "store": False,
        }

        import aiohttp  # noqa: PLC0415 — lazy; keeps module importable without aiohttp

        full_text = ""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                _CHATGPT_BACKEND_URL, headers=headers, json=payload
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"ChatGPT backend error ({resp.status}): {body[:500]}")

                async for raw_line in resp.content:
                    line = raw_line.decode("utf-8").strip()
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    etype = event.get("type", "")
                    if etype == "response.output_text.delta":
                        full_text += event.get("delta", "")
                    elif etype == "response.completed":
                        # Extract final text from completed response
                        resp_obj = event.get("response", {})
                        for item in resp_obj.get("output", []):
                            if item.get("type") == "message":
                                for block in item.get("content", []):
                                    if block.get("type") == "output_text":
                                        full_text = block["text"]

        if not full_text:
            raise RuntimeError("No text output in ChatGPT backend response")
        return full_text

    async def _synthesize_stream_uncached(self, question, transcript_context=None, prefetched_chunks=None):
        """Synthesize with streaming support. Yields text deltas."""
        if prefetched_chunks is not None:
            results = prefetched_chunks
            self._last_retrieval_ms = 0.0
        elif self._retriever:
            loop = asyncio.get_event_loop()
            t_ret = time.monotonic()
            results = await loop.run_in_executor(
                None, self._retriever.retrieve, question
            )
            self._last_retrieval_ms = round((time.monotonic() - t_ret) * 1000.0, 1)
            logger.info("Retrieved %d chunks for synthesis (%.1f ms)", len(results), self._last_retrieval_ms)
        else:
            results = []
            self._last_retrieval_ms = None

        doc_registry = None
        if self._retriever and hasattr(self._retriever, "get_doc_registry"):
            try:
                doc_registry = self._retriever.get_doc_registry()
            except (FileNotFoundError, OSError, json.JSONDecodeError):
                doc_registry = None
            except Exception as e:
                logger.warning("Failed to load doc registry for synthesis: %s", e)
                doc_registry = None

        user_prompt = build_user_prompt(
            question, results, doc_registry=doc_registry, transcript_context=transcript_context
        )

        # Stream deltas
        if self._oauth_token and self._chatgpt_account_id:
            async for delta in self._call_chatgpt_backend_stream(user_prompt):
                yield delta
        else:
            async for delta in self._call_openai_api_stream(user_prompt):
                yield delta

    async def _call_openai_api_stream(self, user_prompt: str) -> AsyncGenerator[str, None]:
        """OpenAI API streaming call."""
        response = await self._client.chat.completions.create(
            model=self._config.model,
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            stream=True,
        )
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def _call_chatgpt_backend_stream(self, user_prompt: str) -> AsyncGenerator[str, None]:
        """ChatGPT backend streaming call."""
        headers = {
            "Authorization": f"Bearer {self._oauth_token}",
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
            "chatgpt-account-id": self._chatgpt_account_id,
            "originator": "codex_cli_rs",
        }
        payload = {
            "model": self._oauth_model,
            "instructions": SYSTEM_PROMPT,
            "input": [
                {"role": "user", "content": user_prompt},
            ],
            "stream": True,
            "store": False,
        }

        import aiohttp  # noqa: PLC0415 — lazy; keeps module importable without aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.post(
                _CHATGPT_BACKEND_URL, headers=headers, json=payload
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"ChatGPT backend error ({resp.status}): {body[:500]}")

                async for raw_line in resp.content:
                    line = raw_line.decode("utf-8").strip()
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    etype = event.get("type", "")
                    if etype == "response.output_text.delta":
                        delta = event.get("delta", "")
                        if delta:
                            yield delta
