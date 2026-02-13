from __future__ import annotations

from ingest.store import RetrievalResult

SYSTEM_PROMPT = """\
You are a meeting assistant. You answer questions based ONLY on evidence from provided source documents.

CRITICAL RULES:
- Evidence-first: ONLY cite facts that appear in the provided source chunks.
- NEVER fabricate citations, document titles, section names, or page numbers.
- NEVER fabricate compliance claims (SOC2, ISO, HIPAA, etc.) unless they appear verbatim in sources.
- If insufficient evidence exists, say "Not found in sources" and suggest clarifying questions.
- Clearly separate "Evidence from sources" bullets from "Common practice (not confirmed)" bullets.

OUTPUT FORMAT — respond with valid JSON only, no markdown fencing:
{
  "one_liner": "One sentence answer, max 25 words",
  "bullets": ["6-10 evidence-backed bullet points"],
  "best_practice_bullets": ["0-3 general best-practice points NOT from sources, clearly labeled"],
  "clarifiers": ["0-2 clarifying questions if evidence is thin"],
  "citations": [
    {"doc": "document title", "section": "section heading", "page": 5, "quote": "short verbatim quote"}
  ],
  "confidence": 0.0
}

- confidence: 0.0-1.0 based on how well sources answer the question.
- If no relevant sources are provided, set confidence to 0.0 and use clarifiers.
"""


def format_chunks(results: list[RetrievalResult]) -> str:
    """Format retrieved chunks as numbered context for the prompt."""
    if not results:
        return "(No source documents available)"

    parts: list[str] = []
    for i, r in enumerate(results, 1):
        header = f"[{i}] {r.doc_title}"
        if r.section_heading:
            header += f" > {r.section_heading}"
        if r.page_number:
            header += f" (p.{r.page_number})"
        header += f"  [score: {r.score:.2f}]"
        parts.append(f"{header}\n{r.text}")

    return "\n\n".join(parts)


def format_doc_registry(doc_registry: dict, available_titles: set[str]) -> str:
    """Format a document registry preamble for the prompt."""
    if not doc_registry:
        return ""

    lines = ["DOCUMENT REGISTRY (your available knowledge base):"]

    # Only include docs that are actually present in the vector store (or retrieved)
    items = []
    for title, meta in doc_registry.items():
        if title not in available_titles:
            continue
        if not isinstance(meta, dict):
            meta = {}
        pr = (meta.get("priority") or "normal").upper()
        desc = (meta.get("description") or "").strip()
        if desc:
            items.append((title, pr, desc))
        else:
            items.append((title, pr, ""))

    if not items:
        return ""

    for i, (title, pr, desc) in enumerate(items, 1):
        if desc:
            lines.append(f"{i}. [{pr}] \"{title}\" — {desc}")
        else:
            lines.append(f"{i}. [{pr}] \"{title}\"")

    lines.append("")
    lines.append("Prefer HIGH priority documents when sources conflict.")
    return "\n".join(lines).strip() + "\n\n"


def build_user_prompt(
    question: str,
    results: list[RetrievalResult],
    doc_registry: dict | None = None,
    transcript_context: str | None = None,
) -> str:
    """Assemble the full user prompt with question and context."""
    chunks_text = format_chunks(results)
    titles = {r.doc_title for r in results}
    registry_text = format_doc_registry(doc_registry or {}, titles)

    parts = [f"ACTIVE QUESTION: {question}\n"]

    # Add recent conversation context if provided
    if transcript_context and transcript_context.strip():
        parts.append(f"RECENT CONVERSATION:\n{transcript_context.strip()}\n")

    parts.extend([
        f"{registry_text}"
        f"SOURCE DOCUMENTS:\n{chunks_text}\n\n"
        "Provide your answer as JSON."
    ])

    return "".join(parts)
