from __future__ import annotations

import logging
from pathlib import Path

from ingest.config import IngestConfig
from ingest.embedder import Embedder
from ingest.store import ProjectStore, RetrievalResult

logger = logging.getLogger(__name__)


class Retriever:
    """Thin retrieval API used by the backend at runtime."""

    def __init__(self, project_path: Path, config: IngestConfig) -> None:
        self._store = ProjectStore(project_path, config.retrieval)
        self._embedder = Embedder(config.embedding)
        self._config = config

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievalResult]:
        """Embed query and search the store. Returns ranked results."""
        embedding = self._embedder.embed_query(query)
        results = self._store.search(
            embedding,
            top_k=top_k or self._config.retrieval.top_k,
        )
        logger.debug("Retrieved %d results for: %s", len(results), query[:80])
        return results
