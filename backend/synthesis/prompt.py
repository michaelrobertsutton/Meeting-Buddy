from __future__ import annotations

from ingest.store import RetrievalResult

SYSTEM_PROMPT = """\
You are a meeting assistant. You answer questions based on evidence from provided source documents, \
with transparent inference when direct matches are weak.

CRITICAL RULES:
- Evidence-first: prefer facts that appear in the provided source chunks.
- NEVER fabricate citations, document titles, section names, or page numbers.
- NEVER fabricate compliance claims (SOC2, ISO, HIPAA, etc.) unless they appear verbatim in sources.
- Semantic fallback: if the question uses a term not in the sources (e.g. "SLA" but sources say \
"Remediation Timeline", or "offboarding" but sources say "account termination"), pivot to the \
adjacent concept, use it to answer, and report the synonym mapping transparently in one_liner.
- Synonym cluster examples: SLA↔"service level"↔"response time"↔"remediation timeline"; \
offboarding↔"account termination"↔"deprovisioning"; incident↔"breach"↔"security event".
- When using inference or adjacency, set inferred=true and explain the reasoning field.
- NEVER fabricate — if no adjacent concept exists, say so and set confidence=0.

RESPONSE LAYERS — respond with valid JSON only, no markdown fencing:
{
  "one_liner": "One sentence answer, max 25 words. Note synonym mapping if used.",
  "bullets": ["4-8 Layer 1 facts: direct evidence from sources"],
  "process_bullets": ["0-4 Layer 2 bullets: how to act on this — execution steps, process guidance"],
  "best_practice_bullets": ["0-2 general best-practice points NOT from sources, clearly labeled"],
  "next_step": "Single most important follow-up action, or empty string if none",
  "clarifiers": ["0-2 clarifying questions if evidence is thin"],
  "citations": [
    {"doc": "document title", "section": "section heading", "page": 5, "quote": "short verbatim quote"}
  ],
  "confidence": 0.0,
  "inferred": false,
  "reasoning": ""
}

- confidence: 0.0-1.0 based on how well sources answer the question.
- inferred: true if the answer relies on semantic inference / synonym pivoting rather than direct match.
- reasoning: brief explanation of the inference (e.g. "SLA not found; answered using Remediation Timeline (p.4) which defines response windows"). Empty string when inferred=false.
- process_bullets: Layer 2 — execution context. Examples: "To act on this, escalate to your CSM", \
"Check the runbook at section 3.2 for step-by-step instructions".
- next_step: single actionable follow-up the meeting participant should take right now.
- If no relevant sources exist, set confidence=0.0 and populate clarifiers.
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
