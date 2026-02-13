from __future__ import annotations

import logging

import numpy as np

from ingest.config import EmbeddingConfig

logger = logging.getLogger(__name__)


class Embedder:
    """Wraps sentence-transformers for embedding text chunks."""

    def __init__(self, config: EmbeddingConfig) -> None:
        self._config = config
        self._model = None

    def _load_model(self):
        from sentence_transformers import SentenceTransformer

        device = self._config.device
        try:
            self._model = SentenceTransformer(self._config.model_name, device=device)
            logger.info("Loaded embedding model %s on %s", self._config.model_name, device)
        except Exception:
            if device != "cpu":
                logger.warning("Failed to load on %s, falling back to cpu", device)
                self._model = SentenceTransformer(self._config.model_name, device="cpu")
                logger.info("Loaded embedding model %s on cpu", self._config.model_name)
            else:
                raise

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        """Embed a list of texts, returning (N, dim) float32 array."""
        if self._model is None:
            self._load_model()

        embeddings = self._model.encode(
            texts,
            batch_size=self._config.batch_size,
            show_progress_bar=len(texts) > 100,
            normalize_embeddings=True,
        )
        return np.asarray(embeddings, dtype=np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        """Embed a single query string, returning (dim,) float32 array."""
        result = self.embed_texts([query])
        return result[0]
