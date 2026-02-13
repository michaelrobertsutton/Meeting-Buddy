from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field

import aiohttp

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
    best_practice_bullets: list[str] = field(default_factory=list)
    clarifiers: list[str] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "one_liner": self.one_liner,
            "bullets": self.bullets,
            "best_practice_bullets": self.best_practice_bullets,
            "clarifiers": self.clarifiers,
            "citations": self.citations,
            "confidence": self.confidence,
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

    def set_retriever(self, retriever) -> None:
        """Swap the retriever (e.g. after project switch)."""
        self._retriever = retriever
        self._last_question = None
        self._last_result = None

    async def synthesize(self, question: str) -> SynthesisResult | None:
        """Synthesize an answer for the given question. Returns None if unchanged."""
        if question == self._last_question:
            return None

        self._last_question = question

        # Retrieve context chunks
        results = []
        if self._retriever:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None, self._retriever.retrieve, question
            )
            logger.info("Retrieved %d chunks for synthesis", len(results))

        doc_registry = None
        if self._retriever and hasattr(self._retriever, "get_doc_registry"):
            try:
                doc_registry = self._retriever.get_doc_registry()
            except Exception:
                doc_registry = None

        user_prompt = build_user_prompt(question, results, doc_registry=doc_registry)

        try:
            if self._oauth_token and self._chatgpt_account_id:
                content = await self._call_chatgpt_backend(user_prompt)
            else:
                content = await self._call_openai_api(user_prompt)

            data = json.loads(content)

            result = SynthesisResult(
                one_liner=data.get("one_liner", ""),
                bullets=data.get("bullets", []),
                best_practice_bullets=data.get("best_practice_bullets", []),
                clarifiers=data.get("clarifiers", []),
                citations=data.get("citations", []),
                confidence=float(data.get("confidence", 0.0)),
            )

            # Validate citations
            if results:
                valid_titles = {r.doc_title for r in results}
                result.citations = [
                    c for c in result.citations
                    if c.get("doc") in valid_titles
                ]

            self._last_result = result
            logger.info(
                "Synthesis complete: %d bullets, confidence=%.2f",
                len(result.bullets), result.confidence,
            )
            return result

        except Exception:
            logger.exception("Synthesis failed")
            return None

    async def _call_openai_api(self, user_prompt: str) -> str:
        """Standard OpenAI API call (platform billing)."""
        response = await self._client.chat.completions.create(
            model=self._config.model,
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content

    async def _call_chatgpt_backend(self, user_prompt: str) -> str:
        """ChatGPT backend call via SSE streaming (uses Plus/Pro subscription quota)."""
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
            "instructions": SYSTEM_PROMPT,
            "input": [
                {"role": "user", "content": user_prompt},
            ],
            "stream": True,
            "store": False,
        }

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
