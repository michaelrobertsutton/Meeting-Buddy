from __future__ import annotations

import logging
from pathlib import Path

from ingest.config import IngestConfig
from ingest.embedder import Embedder
from ingest.store import ProjectStore, RetrievalResult

logger = logging.getLogger(__name__)


class Retriever:
    """Thin retrieval API used by the backend at runtime."""

    PRIORITY_WEIGHTS = {
        "high": 1.5,
        "normal": 1.0,
        "low": 0.5,
    }

    def __init__(self, project_path: Path, config: IngestConfig) -> None:
        self._project_path = project_path
        self._store = ProjectStore(project_path, config.retrieval)
        self._embedder = Embedder(config.embedding)
        self._config = config

    def get_doc_registry(self) -> dict:
        """Return doc_registry from this project's metadata.json."""
        try:
            meta_path = self._project_path / "metadata.json"
            if not meta_path.exists():
                return {}
            import json
            meta = json.loads(meta_path.read_text())
            reg = meta.get("doc_registry")
            return reg if isinstance(reg, dict) else {}
        except Exception:
            logger.debug("Failed to read doc_registry", exc_info=True)
            return {}

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievalResult]:
        """Embed query and search the store. Returns ranked results."""
        embedding = self._embedder.embed_query(query)

        k = top_k or self._config.retrieval.top_k
        # Pull a few extra candidates so boosting can re-rank meaningfully
        raw = self._store.search(embedding, top_k=max(k * 3, k))

        registry = self.get_doc_registry()
        for r in raw:
            meta = registry.get(r.doc_title) if isinstance(registry, dict) else None
            priority = (meta or {}).get("priority", "normal")
            weight = self.PRIORITY_WEIGHTS.get(priority, 1.0)
            r.score *= weight

        raw.sort(key=lambda x: x.score, reverse=True)
        results = raw[:k]

        logger.debug("Retrieved %d results for: %s", len(results), query[:80])
        return results
