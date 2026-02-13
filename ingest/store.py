from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ingest.chunker import Chunk
from ingest.config import RetrievalConfig

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    text: str
    doc_title: str
    section_heading: str
    page_number: int | None
    score: float
    source_path: str


class ProjectStore:
    """Per-project LanceDB vector store."""

    TABLE_NAME = "chunks"

    def __init__(self, project_path: Path, retrieval_config: RetrievalConfig | None = None) -> None:
        self._project_path = project_path
        self._lance_path = project_path / "lance"
        self._retrieval_config = retrieval_config or RetrievalConfig()
        self._db = None
        self._table = None

    def _open(self):
        import lancedb

        self._lance_path.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(self._lance_path))

        if self.TABLE_NAME in self._db.table_names():
            self._table = self._db.open_table(self.TABLE_NAME)
        else:
            self._table = None

    def _ensure_open(self):
        if self._db is None:
            self._open()

    def add_chunks(self, chunks: list[Chunk], embeddings: np.ndarray) -> None:
        """Insert chunks with their embeddings into the store."""
        self._ensure_open()

        records = []
        for chunk, vec in zip(chunks, embeddings):
            records.append({
                "vector": vec.tolist(),
                "text": chunk.text,
                "doc_title": chunk.doc_title,
                "source_path": chunk.source_path,
                "section_heading": chunk.section_heading,
                "page_number": chunk.page_number or 0,
                "chunk_index": chunk.chunk_index,
            })

        if self._table is None:
            self._table = self._db.create_table(self.TABLE_NAME, data=records)
        else:
            self._table.add(records)

        logger.info("Added %d chunks to store", len(records))

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int | None = None,
        min_score: float | None = None,
    ) -> list[RetrievalResult]:
        """Search for similar chunks. Returns results sorted by score descending."""
        self._ensure_open()

        if self._table is None:
            return []

        k = top_k or self._retrieval_config.top_k
        threshold = min_score if min_score is not None else self._retrieval_config.min_score

        results = (
            self._table.search(query_embedding.tolist())
            .metric("cosine")
            .limit(k)
            .to_list()
        )

        out: list[RetrievalResult] = []
        for row in results:
            # LanceDB returns _distance (L2) by default; lower = better
            # With cosine metric, _distance is 1 - cosine_similarity
            distance = row.get("_distance", 1.0)
            score = 1.0 - distance

            if score < threshold:
                continue

            out.append(RetrievalResult(
                text=row["text"],
                doc_title=row["doc_title"],
                section_heading=row["section_heading"],
                page_number=row["page_number"] if row["page_number"] != 0 else None,
                score=score,
                source_path=row["source_path"],
            ))

        return out

    def list_documents(self) -> list[str]:
        """Return distinct document titles in the store."""
        return [d["title"] for d in self.list_document_details()]

    def list_document_details(self) -> list[dict]:
        """Return distinct documents with lightweight metadata for UI.

        Output: [{title, source_path, size_bytes, indexed}]
        """
        self._ensure_open()
        if self._table is None:
            return []

        table = self._table.to_arrow()
        titles = table.column("doc_title").to_pylist()
        paths = table.column("source_path").to_pylist()

        # Use first seen source_path per title
        first_path: dict[str, str] = {}
        for t, p in zip(titles, paths):
            if t not in first_path:
                first_path[t] = p

        out: list[dict] = []
        for title in sorted(first_path.keys()):
            sp = first_path.get(title, "")
            size = 0
            try:
                if sp and Path(sp).exists():
                    size = Path(sp).stat().st_size
            except Exception:
                size = 0
            out.append({
                "title": title,
                "source_path": sp,
                "size_bytes": size,
                "indexed": True,
            })

        return out

    def delete_document(self, doc_title: str) -> int:
        """Delete all chunks for a document. Returns count deleted."""
        self._ensure_open()
        if self._table is None:
            return 0

        before = self._table.count_rows()
        self._table.delete(f"doc_title = '{doc_title}'")
        after = self._table.count_rows()
        count = before - after
        if count > 0:
            logger.info("Deleted %d chunks for '%s'", count, doc_title)
        return count

    def chunk_count(self) -> int:
        """Return total number of chunks in the store."""
        self._ensure_open()
        if self._table is None:
            return 0
        return self._table.count_rows()
