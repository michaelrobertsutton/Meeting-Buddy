from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path("~/.meeting-buddy").expanduser()
_CONFIG_FILE = _CONFIG_DIR / "config.json"


@dataclass
class AppSettings:
    openai_api_key: str = ""
    active_project: str = ""
    synthesis_model: str = "gpt-4o-mini"
    auth_method: str = "api_key"  # "api_key" or "oauth"


class SettingsManager:
    """Persists app settings to ~/.meeting-buddy/config.json."""

    def __init__(self, token_manager=None) -> None:
        self._settings = AppSettings()
        self._token_manager = token_manager
        self.load()

    def load(self) -> None:
        if _CONFIG_FILE.exists():
            try:
                data = json.loads(_CONFIG_FILE.read_text())
                self._settings = AppSettings(
                    openai_api_key=data.get("openai_api_key", ""),
                    active_project=data.get("active_project", ""),
                    synthesis_model=data.get("synthesis_model", "gpt-4o-mini"),
                    auth_method=data.get("auth_method", "api_key"),
                )
                logger.info("Settings loaded from %s", _CONFIG_FILE)
            except (json.JSONDecodeError, OSError):
                logger.warning("Failed to load settings, using defaults")
        else:
            logger.info("No settings file found, using defaults")

    def save(self) -> None:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _CONFIG_FILE.write_text(json.dumps(asdict(self._settings), indent=2))
        logger.info("Settings saved to %s", _CONFIG_FILE)

    @property
    def settings(self) -> AppSettings:
        return self._settings

    def get_api_key(self) -> str:
        """Return OAuth API key if available, else saved key, else env var."""
        if (
            self._settings.auth_method == "oauth"
            and self._token_manager
            and self._token_manager.has_tokens()
        ):
            return self._token_manager.get_api_key()
        return self._settings.openai_api_key or os.environ.get("OPENAI_API_KEY", "")

    def set_api_key(self, key: str) -> None:
        self._settings.openai_api_key = key
        self.save()

    def get_active_project(self, cli_override: str | None = None) -> str:
        """CLI --project takes precedence over saved setting."""
        if cli_override:
            return cli_override
        return self._settings.active_project

    def set_auth_method(self, method: str) -> None:
        self._settings.auth_method = method
        self.save()

    def set_token_manager(self, tm) -> None:
        self._token_manager = tm

    def set_active_project(self, name: str) -> None:
        self._settings.active_project = name
        self.save()

    def get_synthesis_model(self) -> str:
        return self._settings.synthesis_model

    def to_safe_dict(self) -> dict:
        """Return settings with masked API key (never send raw key to frontend)."""
        key = self._settings.openai_api_key
        masked = ""
        if key:
            masked = key[:3] + "..." + key[-4:] if len(key) > 10 else "***"
        if self._token_manager:
            oauth_status = self._token_manager.to_status_dict()
        else:
            oauth_status = {"logged_in": False, "email": "", "expires_at_ms": 0}

        return {
            "openai_api_key_masked": masked,
            "has_api_key": bool(self.get_api_key()),
            "active_project": self._settings.active_project,
            "synthesis_model": self._settings.synthesis_model,
            "auth_method": self._settings.auth_method,
            "oauth_status": oauth_status,
        }
