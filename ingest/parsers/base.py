from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class ParsedSection:
    text: str
    heading: str = ""
    page_number: int | None = None


@dataclass
class ParsedDocument:
    title: str
    source_path: str
    sections: list[ParsedSection] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class DocumentParser(Protocol):
    def can_parse(self, path: Path) -> bool: ...
    def parse(self, path: Path) -> ParsedDocument: ...
