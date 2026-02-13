from __future__ import annotations

import logging
from pathlib import Path

from ingest.chunker import chunk_document
from ingest.config import IngestConfig
from ingest.embedder import Embedder
from ingest.parsers.registry import SUPPORTED_EXTENSIONS, parse_document
from ingest.project_manager import ProjectManager
from ingest.store import ProjectStore

logger = logging.getLogger(__name__)


class IngestPipeline:
    """Orchestrates: parse -> chunk -> embed -> store."""

    def __init__(self, config: IngestConfig) -> None:
        self._config = config
        self._embedder = Embedder(config.embedding)
        self._manager = ProjectManager(config.project)

    def ingest_file(self, project_name: str, file_path: str | Path) -> int:
        """Ingest a single file into a project. Returns chunk count."""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        project_path = self._manager.get_project_path(project_name)
        if not project_path.exists():
            self._manager.create_project(project_name)

        store = ProjectStore(project_path, self._config.retrieval)

        logger.info("Parsing %s", file_path.name)
        doc = parse_document(file_path)

        logger.info("Chunking (got %d sections)", len(doc.sections))
        chunks = chunk_document(doc, self._config.chunking)

        if not chunks:
            logger.warning("No chunks produced from %s", file_path.name)
            return 0

        logger.info("Embedding %d chunks", len(chunks))
        texts = [c.text for c in chunks]
        embeddings = self._embedder.embed_texts(texts)

        logger.info("Storing chunks")
        store.add_chunks(chunks, embeddings)

        logger.info("Ingested %s: %d chunks", file_path.name, len(chunks))
        return len(chunks)

    def ingest_directory(
        self,
        project_name: str,
        dir_path: str | Path,
        recursive: bool = True,
    ) -> int:
        """Ingest all supported files in a directory. Returns total chunk count."""
        dir_path = Path(dir_path)
        if not dir_path.is_dir():
            raise NotADirectoryError(f"Not a directory: {dir_path}")

        total = 0
        pattern = "**/*" if recursive else "*"
        files = sorted(
            f for f in dir_path.glob(pattern)
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        )

        if not files:
            logger.warning("No supported files found in %s", dir_path)
            return 0

        logger.info("Found %d files to ingest in %s", len(files), dir_path)
        for f in files:
            try:
                count = self.ingest_file(project_name, f)
                total += count
            except Exception as e:
                logger.error("Failed to ingest %s: %s", f.name, e)

        return total
