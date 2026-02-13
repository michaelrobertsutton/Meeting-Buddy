from __future__ import annotations

from pathlib import Path

from ingest.parsers.base import DocumentParser, ParsedDocument
from ingest.parsers.docx_parser import DOCXParser
from ingest.parsers.html_parser import HTMLParser
from ingest.parsers.markdown_parser import MarkdownParser
from ingest.parsers.pdf_parser import PDFParser

_PARSERS: list[DocumentParser] = [
    PDFParser(),
    DOCXParser(),
    MarkdownParser(),
    HTMLParser(),
]

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".md", ".html", ".htm"}


def get_parser(path: Path) -> DocumentParser | None:
    """Return the appropriate parser for the given file, or None."""
    for parser in _PARSERS:
        if parser.can_parse(path):
            return parser
    return None


def parse_document(path: Path) -> ParsedDocument:
    """Parse a document, raising ValueError if unsupported."""
    parser = get_parser(path)
    if parser is None:
        raise ValueError(f"Unsupported file type: {path.suffix}")
    return parser.parse(path)
