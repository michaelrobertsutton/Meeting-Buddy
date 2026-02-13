from __future__ import annotations

import re
from pathlib import Path

from ingest.parsers.base import ParsedDocument, ParsedSection


class MarkdownParser:
    """Parse Markdown files by splitting on heading lines."""

    _HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower() == ".md"

    def parse(self, path: Path) -> ParsedDocument:
        content = path.read_text(encoding="utf-8", errors="replace")
        sections: list[ParsedSection] = []

        # Find all heading positions
        headings = list(self._HEADING_RE.finditer(content))

        if not headings:
            # No headings — entire file is one section
            text = content.strip()
            if text:
                sections.append(ParsedSection(text=text, heading=""))
        else:
            # Text before first heading
            before = content[: headings[0].start()].strip()
            if before:
                sections.append(ParsedSection(text=before, heading=""))

            for i, match in enumerate(headings):
                heading_text = match.group(2).strip()
                start = match.end()
                end = headings[i + 1].start() if i + 1 < len(headings) else len(content)
                body = content[start:end].strip()
                if body:
                    sections.append(ParsedSection(text=body, heading=heading_text))

        if not sections:
            sections.append(ParsedSection(text="", heading=""))

        return ParsedDocument(
            title=path.stem,
            source_path=str(path),
            sections=sections,
        )
