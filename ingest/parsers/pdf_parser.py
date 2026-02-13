from __future__ import annotations

from pathlib import Path

from ingest.parsers.base import ParsedDocument, ParsedSection


class PDFParser:
    """Parse PDF files using PyMuPDF (fitz)."""

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    def parse(self, path: Path) -> ParsedDocument:
        import fitz  # PyMuPDF

        doc = fitz.open(str(path))
        sections: list[ParsedSection] = []
        current_heading = ""

        for page_num in range(len(doc)):
            page = doc[page_num]
            blocks = page.get_text("dict")["blocks"]

            page_texts: list[str] = []
            for block in blocks:
                if block["type"] != 0:  # text blocks only
                    continue
                for line in block["lines"]:
                    line_text = "".join(span["text"] for span in line["spans"]).strip()
                    if not line_text:
                        continue

                    # Heading heuristic: large font or bold
                    max_size = max(span["size"] for span in line["spans"])
                    is_bold = any("bold" in span.get("font", "").lower() for span in line["spans"])

                    if max_size >= 14 or (is_bold and max_size >= 12):
                        # Flush accumulated text as a section
                        if page_texts:
                            sections.append(ParsedSection(
                                text="\n".join(page_texts),
                                heading=current_heading,
                                page_number=page_num + 1,
                            ))
                            page_texts = []
                        current_heading = line_text
                    else:
                        page_texts.append(line_text)

            if page_texts:
                sections.append(ParsedSection(
                    text="\n".join(page_texts),
                    heading=current_heading,
                    page_number=page_num + 1,
                ))

        doc.close()

        # If no sections were created (e.g. scanned PDF with no text), create empty
        if not sections:
            sections.append(ParsedSection(text="", heading="", page_number=1))

        return ParsedDocument(
            title=path.stem,
            source_path=str(path),
            sections=sections,
        )
