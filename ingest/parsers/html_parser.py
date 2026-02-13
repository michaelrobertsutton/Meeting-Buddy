from __future__ import annotations

from pathlib import Path

from ingest.parsers.base import ParsedDocument, ParsedSection


class HTMLParser:
    """Parse HTML files using BeautifulSoup, splitting on heading tags."""

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower() in (".html", ".htm")

    def parse(self, path: Path) -> ParsedDocument:
        from bs4 import BeautifulSoup

        content = path.read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(content, "html.parser")

        # Remove script and style elements
        for tag in soup(["script", "style"]):
            tag.decompose()

        heading_tags = {"h1", "h2", "h3", "h4", "h5", "h6"}
        sections: list[ParsedSection] = []
        current_heading = ""
        current_texts: list[str] = []

        for element in soup.body.children if soup.body else soup.children:
            if hasattr(element, "name") and element.name in heading_tags:
                # Flush current section
                if current_texts:
                    sections.append(ParsedSection(
                        text="\n".join(current_texts),
                        heading=current_heading,
                    ))
                    current_texts = []
                current_heading = element.get_text(strip=True)
            else:
                text = element.get_text(strip=True) if hasattr(element, "get_text") else str(element).strip()
                if text:
                    current_texts.append(text)

        if current_texts:
            sections.append(ParsedSection(
                text="\n".join(current_texts),
                heading=current_heading,
            ))

        if not sections:
            # Fallback: just get all text
            all_text = soup.get_text(separator="\n", strip=True)
            sections.append(ParsedSection(text=all_text, heading=""))

        # Extract title
        title = path.stem
        title_tag = soup.find("title")
        if title_tag and title_tag.string:
            title = title_tag.string.strip()

        return ParsedDocument(
            title=title,
            source_path=str(path),
            sections=sections,
        )
