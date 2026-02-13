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
    """Manages project directories under the base path.

    Each project directory contains a metadata.json file. We treat it as the
    project "config" and store per-document metadata there (doc registry).

    metadata.json schema (additive):
    {
      "display_name": "My Project",
      "doc_registry": {
        "Some Doc.pdf": {
          "description": "One-line description...",
          "priority": "high" | "normal" | "low"
        }
      }
    }
    """

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
            meta_file.write_text(json.dumps({"display_name": name, "doc_registry": {}}, indent=2))
            logger.info("Created project '%s' at %s", name, path)
        else:
            # Ensure required top-level keys exist (non-destructive)
            try:
                meta = self._read_metadata(path)
                changed = False
                if "display_name" not in meta:
                    meta["display_name"] = name
                    changed = True
                if "doc_registry" not in meta or not isinstance(meta.get("doc_registry"), dict):
                    meta["doc_registry"] = {}
                    changed = True
                if changed:
                    self._write_metadata(path, meta)
            except Exception:
                pass
            logger.info("Project '%s' already exists at %s", name, path)

        return path

    def list_projects(self) -> list[dict]:
        """Return list of {name, slug, path} for all projects."""
        if not self._base_path.exists():
            return []

        projects = []
        for d in sorted(self._base_path.iterdir()):
            if not d.is_dir():
                continue
            display_name = d.name
            try:
                meta = self._read_metadata(d)
                display_name = meta.get("display_name", d.name)
            except Exception:
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

    # --- Metadata helpers ---

    def _metadata_path(self, project_path: Path) -> Path:
        return project_path / "metadata.json"

    def _read_metadata(self, project_path: Path) -> dict:
        meta_file = self._metadata_path(project_path)
        if not meta_file.exists():
            return {}
        return json.loads(meta_file.read_text())

    def _write_metadata(self, project_path: Path, meta: dict) -> None:
        meta_file = self._metadata_path(project_path)
        meta_file.write_text(json.dumps(meta, indent=2, sort_keys=True))

    def get_project_metadata(self, name: str) -> dict:
        """Return metadata.json content for a project (empty dict if missing)."""
        path = self._project_path(name)
        return self._read_metadata(path) if path.exists() else {}

    def get_doc_registry(self, name: str) -> dict:
        meta = self.get_project_metadata(name)
        reg = meta.get("doc_registry")
        return reg if isinstance(reg, dict) else {}

    def update_doc_meta(
        self,
        name: str,
        doc_title: str,
        description: str | None = None,
        priority: str | None = None,
    ) -> dict:
        """Update per-doc metadata in metadata.json. Returns updated entry."""
        if priority is not None and priority not in ("high", "normal", "low"):
            raise ValueError("priority must be one of: high, normal, low")

        path = self._project_path(name)
        if not path.exists():
            raise ValueError(f"Project '{name}' not found")

        meta = self._read_metadata(path)
        if "display_name" not in meta:
            meta["display_name"] = name
        reg = meta.get("doc_registry")
        if not isinstance(reg, dict):
            reg = {}
            meta["doc_registry"] = reg

        entry = reg.get(doc_title) or {"description": "", "priority": "normal"}
        if description is not None:
            entry["description"] = description.strip()
        if priority is not None:
            entry["priority"] = priority
        reg[doc_title] = entry

        self._write_metadata(path, meta)
        return entry

    def ensure_doc_registry_entry(
        self,
        name: str,
        doc_title: str,
        suggested_description: str | None = None,
    ) -> dict:
        """Ensure doc_registry has an entry for doc_title. Returns entry."""
        path = self._project_path(name)
        if not path.exists():
            self.create_project(name)

        meta = self._read_metadata(path)
        if "display_name" not in meta:
            meta["display_name"] = name
        reg = meta.get("doc_registry")
        if not isinstance(reg, dict):
            reg = {}
            meta["doc_registry"] = reg

        entry = reg.get(doc_title)
        if not entry:
            desc = (suggested_description or "").strip()
            reg[doc_title] = {
                "description": desc,
                "priority": "normal",
            }
            self._write_metadata(path, meta)
        return reg.get(doc_title, {})

    def delete_project(self, name: str) -> bool:
        """Delete a project directory. Returns True if deleted."""
        import shutil

        path = self._project_path(name)
        if path.exists():
            shutil.rmtree(path)
            logger.info("Deleted project '%s' at %s", name, path)
            return True
        return False
