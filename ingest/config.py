from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChunkingConfig:
    chunk_size: int = 512  # words
    chunk_overlap: int = 64  # words
    min_chunk_size: int = 50  # words


@dataclass
class EmbeddingConfig:
    model_name: str = "all-MiniLM-L6-v2"
    device: str = "mps"  # fallback to cpu at runtime
    batch_size: int = 32


@dataclass
class RetrievalConfig:
    top_k: int = 8
    min_score: float = 0.25


@dataclass
class ProjectConfig:
    base_path: str = "~/.meeting-buddy/projects"


@dataclass
class IngestConfig:
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    project: ProjectConfig = field(default_factory=ProjectConfig)
