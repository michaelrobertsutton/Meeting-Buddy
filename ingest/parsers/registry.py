from __future__ import annotations

from pathlib import Path

from ingest.parsers.base import DocumentParser, ParsedDocument
from ingest.parsers.docx_parser import DOCXParser
from ingest.parsers.html_parser import HTMLParser
from ingest.parsers.markdown_parser import MarkdownParser
from ingest.parsers.pdf_parser import PDFParser
from ingest.parsers.url_parser import URLParser

_PARSERS: list[DocumentParser] = [
    PDFParser(),
    DOCXParser(),
    MarkdownParser(),
    HTMLParser(),
]

_URL_PARSER = URLParser()

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".md", ".html", ".htm"}


def get_parser(path: Path | str) -> DocumentParser | None:
    """Return the appropriate parser for the given file or URL, or None."""
    # Check URL first
    if _URL_PARSER.can_parse(path):
        return _URL_PARSER
    
    # Then check file parsers
    if isinstance(path, str):
        path = Path(path)
    for parser in _PARSERS:
        if parser.can_parse(path):
            return parser
    return None


def parse_document(path: Path | str) -> ParsedDocument:
    """Parse a document or URL, raising ValueError if unsupported."""
    parser = get_parser(path)
    if parser is None:
        if isinstance(path, str) and ("://" in path or path.startswith("http")):
            raise ValueError(f"Unsupported URL format: {path}")
        file_path = Path(path) if isinstance(path, str) else path
        raise ValueError(f"Unsupported file type: {file_path.suffix}")
    return parser.parse(path)
