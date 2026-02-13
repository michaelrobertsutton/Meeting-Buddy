from ingest.chunker import chunk_document
from ingest.config import ChunkingConfig
from ingest.parsers.base import ParsedDocument, ParsedSection


def test_chunk_document_produces_chunks():
    doc = ParsedDocument(
        title="Doc",
        source_path="/tmp/doc.txt",
        sections=[ParsedSection(text="This is a sentence. This is another sentence. " * 50)],
    )
    chunks = chunk_document(doc, ChunkingConfig(chunk_size=50, chunk_overlap=10, min_chunk_size=10))
    assert len(chunks) > 0
    assert all(c.doc_title == "Doc" for c in chunks)
