from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SessionData:
    """All data needed to render a session export."""

    transcript_segments: list[dict] = field(default_factory=list)
    qa_history: list[dict] = field(default_factory=list)
    project_name: str = ""
    session_start: float = 0.0  # wall-clock time.time()
    session_end: float = 0.0


def render_markdown(session: SessionData) -> str:
    """Render session data as a clean Markdown document."""
    lines: list[str] = []

    # Header
    start_dt = datetime.fromtimestamp(session.session_start)
    end_dt = datetime.fromtimestamp(session.session_end)
    duration_min = max(1, int((session.session_end - session.session_start) / 60))

    lines.append("# Meeting Buddy — Session Export")
    lines.append("")

    meta_parts = [f"**Date:** {start_dt.strftime('%Y-%m-%d %H:%M')}"]
    if session.project_name:
        meta_parts.append(f"**Project:** {session.project_name}")
    meta_parts.append(f"**Duration:** {duration_min} min")
    lines.append("  |  ".join(meta_parts))
    lines.append("")

    # Q&A Summary
    if session.qa_history:
        lines.append("## Q&A Summary")
        lines.append("")
        for entry in session.qa_history:
            question = entry.get("question", "")
            answer = entry.get("answer", {})

            lines.append(f"### Q: {question}")
            lines.append("")

            one_liner = answer.get("one_liner", "")
            if one_liner:
                lines.append(f"**A:** {one_liner}")
                lines.append("")

            for bullet in answer.get("bullets", []):
                lines.append(f"- {bullet}")

            bp_bullets = answer.get("best_practice_bullets", [])
            if bp_bullets:
                lines.append("")
                lines.append("*Common practice (not from sources):*")
                for b in bp_bullets:
                    lines.append(f"- {b}")

            citations = answer.get("citations", [])
            if citations:
                lines.append("")
                for c in citations:
                    parts = [c.get("doc", ""), c.get("section", "")]
                    if c.get("page"):
                        parts.append(f"p.{c['page']}")
                    label = " — ".join(p for p in parts if p)
                    quote = c.get("quote", "")
                    if quote:
                        lines.append(f"> *{label}:* \"{quote}\"")
                    else:
                        lines.append(f"> *{label}*")

            lines.append("")
    else:
        lines.append("## Q&A Summary")
        lines.append("")
        lines.append("*No questions were detected during this session.*")
        lines.append("")

    # Full Transcript
    lines.append("## Full Transcript")
    lines.append("")
    if session.transcript_segments:
        for seg in session.transcript_segments:
            offset_s = seg.get("start_time", 0)
            mm = int(offset_s) // 60
            ss = int(offset_s) % 60
            text = seg.get("text", "").strip()
            if text:
                lines.append(f"[{mm:02d}:{ss:02d}] {text}")
    else:
        lines.append("*No transcript recorded.*")

    lines.append("")
    lines.append("---")
    lines.append(f"*Exported by Meeting Buddy on {end_dt.strftime('%Y-%m-%d %H:%M')}*")
    lines.append("")

    return "\n".join(lines)


def render_json(session: SessionData) -> str:
    """Render session data as a JSON string."""
    start_dt = datetime.fromtimestamp(session.session_start)
    end_dt = datetime.fromtimestamp(session.session_end)

    data = {
        "export_version": 1,
        "session": {
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "duration_seconds": round(session.session_end - session.session_start),
            "project": session.project_name,
        },
        "qa_history": session.qa_history,
        "transcript": session.transcript_segments,
    }
    return json.dumps(data, indent=2, ensure_ascii=False)
