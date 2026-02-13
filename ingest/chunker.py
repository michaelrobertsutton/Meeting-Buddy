from __future__ import annotations

import re
from dataclasses import dataclass, field

from ingest.config import ChunkingConfig
from ingest.parsers.base import ParsedDocument


@dataclass
class Chunk:
    text: str
    doc_title: str
    source_path: str
    section_heading: str
    page_number: int | None
    chunk_index: int
    metadata: dict = field(default_factory=dict)


_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences (simple heuristic)."""
    parts = _SENTENCE_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


def chunk_document(doc: ParsedDocument, config: ChunkingConfig) -> list[Chunk]:
    """Split a parsed document into overlapping word-based chunks."""
    chunks: list[Chunk] = []
    chunk_index = 0

    for section in doc.sections:
        if not section.text.strip():
            continue

        sentences = _split_sentences(section.text)
        if not sentences:
            continue

        # Build chunks from sentences, tracking word counts
        current_words: list[str] = []

        for sentence in sentences:
            words = sentence.split()
            current_words.extend(words)

            if len(current_words) >= config.chunk_size:
                chunk_text = " ".join(current_words)
                chunks.append(Chunk(
                    text=chunk_text,
                    doc_title=doc.title,
                    source_path=doc.source_path,
                    section_heading=section.heading,
                    page_number=section.page_number,
                    chunk_index=chunk_index,
                ))
                chunk_index += 1

                # Keep overlap words from end for next chunk
                if config.chunk_overlap > 0 and len(current_words) > config.chunk_overlap:
                    current_words = current_words[-config.chunk_overlap:]
                else:
                    current_words = []

        # Flush remaining words
        if len(current_words) >= config.min_chunk_size:
            chunk_text = " ".join(current_words)
            chunks.append(Chunk(
                text=chunk_text,
                doc_title=doc.title,
                source_path=doc.source_path,
                section_heading=section.heading,
                page_number=section.page_number,
                chunk_index=chunk_index,
            ))
            chunk_index += 1
        elif current_words and chunks:
            # Append short remainder to last chunk
            chunks[-1].text += " " + " ".join(current_words)

    return chunks
