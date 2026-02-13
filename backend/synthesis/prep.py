from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class PrepQuestion:
    text: str


class PrepQuestionGenerator:
    """Generates likely audience questions from the project's document registry."""

    SYSTEM = """You generate likely questions an audience will ask in a meeting.

Rules:
- Output JSON only: {"questions": ["..."]}
- Questions should be specific, short, and phrased as actual questions.
- Avoid duplicates and near-duplicates.
- Prefer questions that can be answered from the provided document set.
"""

    def __init__(self, synthesis_engine) -> None:
        self._engine = synthesis_engine

    async def generate(self, doc_registry: dict, count: int = 12) -> list[str]:
        # doc_registry: {title: {description, priority}}
        items = []
        for title, meta in (doc_registry or {}).items():
            if not isinstance(meta, dict):
                meta = {}
            pr = (meta.get("priority") or "normal").upper()
            desc = (meta.get("description") or "").strip()
            if desc:
                items.append(f"- [{pr}] {title}: {desc}")
            else:
                items.append(f"- [{pr}] {title}")

        context = "\n".join(items) if items else "(No documents)"

        prompt = (
            f"You are helping prep for a meeting/presentation.\n\n"
            f"AVAILABLE DOCUMENTS:\n{context}\n\n"
            f"Generate {count} likely questions the audience will ask."
        )

        # Use the engine's underlying model without retrieval (we already supply context)
        text = await self._engine.simple_json_call(
            system_instructions=self.SYSTEM,
            user_prompt=prompt,
            max_tokens=800,
        )

        data = json.loads(text)
        questions = data.get("questions", [])
        if not isinstance(questions, list):
            return []

        out: list[str] = []
        seen = set()
        for q in questions:
            if not isinstance(q, str):
                continue
            qq = q.strip()
            if not qq:
                continue
            norm = qq.lower()
            if norm in seen:
                continue
            seen.add(norm)
            out.append(qq)

        return out
