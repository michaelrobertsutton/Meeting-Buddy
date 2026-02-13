from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from ingest.config import ProjectConfig

logger = logging.getLogger(__name__)


def _sanitize_name(name: str) -> str:
    """Convert display name to filesystem-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "default"


class ProjectManager:
    """Manages project directories under the base path."""

    def __init__(self, config: ProjectConfig) -> None:
        self._base_path = Path(config.base_path).expanduser()

    def _project_path(self, name: str) -> Path:
        return self._base_path / _sanitize_name(name)

    def create_project(self, name: str) -> Path:
        """Create a new project directory with metadata. Returns path."""
        path = self._project_path(name)
        path.mkdir(parents=True, exist_ok=True)

        meta_file = path / "metadata.json"
        if not meta_file.exists():
            meta_file.write_text(json.dumps({"display_name": name}, indent=2))
            logger.info("Created project '%s' at %s", name, path)
        else:
            logger.info("Project '%s' already exists at %s", name, path)

        return path

    def list_projects(self) -> list[dict]:
        """Return list of {name, slug, path, chunk_count} for all projects."""
        if not self._base_path.exists():
            return []

        projects = []
        for d in sorted(self._base_path.iterdir()):
            if not d.is_dir():
                continue
            meta_file = d / "metadata.json"
            display_name = d.name
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text())
                    display_name = meta.get("display_name", d.name)
                except (json.JSONDecodeError, OSError):
                    pass
            projects.append({
                "name": display_name,
                "slug": d.name,
                "path": str(d),
            })
        return projects

    def project_exists(self, name: str) -> bool:
        return self._project_path(name).exists()

    def get_project_path(self, name: str) -> Path:
        """Return path for a project (may not exist yet)."""
        return self._project_path(name)

    def delete_project(self, name: str) -> bool:
        """Delete a project directory. Returns True if deleted."""
        import shutil

        path = self._project_path(name)
        if path.exists():
            shutil.rmtree(path)
            logger.info("Deleted project '%s' at %s", name, path)
            return True
        return False
