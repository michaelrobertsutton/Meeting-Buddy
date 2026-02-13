from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import aiohttp

logger = logging.getLogger(__name__)

_TOKEN_FILE = Path("~/.meeting-buddy/oauth_tokens.json").expanduser()


@dataclass
class OAuthConfig:
    client_id: str = "app_EMoamEEZ73f0CkXaXp7hrann"
    auth_url: str = "https://auth.openai.com/oauth/authorize"
    token_url: str = "https://auth.openai.com/oauth/token"
    scopes: str = "openid profile email offline_access"
    redirect_port: int = 1455


@dataclass
class TokenData:
    access_token: str = ""
    refresh_token: str = ""
    id_token: str = ""
    api_key: str = ""
    expires_at_ms: int = 0
    email: str = ""


class TokenManager:
    """Manages OAuth tokens: persistence, refresh, and API access via access_token."""

    def __init__(self, config: OAuthConfig | None = None) -> None:
        self.config = config or OAuthConfig()
        self._tokens = TokenData()
        self.load()

    def load(self) -> None:
        if _TOKEN_FILE.exists():
            try:
                data = json.loads(_TOKEN_FILE.read_text())
                self._tokens = TokenData(
                    access_token=data.get("access_token", ""),
                    refresh_token=data.get("refresh_token", ""),
                    id_token=data.get("id_token", ""),
                    api_key=data.get("api_key", ""),
                    expires_at_ms=data.get("expires_at_ms", 0),
                    email=data.get("email", ""),
                )
                logger.info("OAuth tokens loaded from %s", _TOKEN_FILE)
            except (json.JSONDecodeError, OSError):
                logger.warning("Failed to load OAuth tokens, starting fresh")
        else:
            logger.info("No OAuth tokens found")

    def save(self) -> None:
        _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_FILE.write_text(json.dumps(asdict(self._tokens), indent=2))
        # Restrict file permissions (owner read/write only)
        _TOKEN_FILE.chmod(0o600)
        logger.info("OAuth tokens saved")

    def has_tokens(self) -> bool:
        return bool(self._tokens.access_token)

    def get_api_key(self) -> str | None:
        """Return the OAuth access_token for use as a Bearer token with the OpenAI API."""
        if not self._tokens.access_token:
            return None
        return self._tokens.access_token

    def get_chatgpt_account_id(self) -> str | None:
        """Extract chatgpt_account_id from JWT id_token claims."""
        return _extract_chatgpt_account_id(self._tokens.id_token)

    def get_email(self) -> str:
        return self._tokens.email

    def get_expires_at_ms(self) -> int:
        return self._tokens.expires_at_ms

    def needs_refresh(self) -> bool:
        if not self._tokens.refresh_token:
            return False
        now_ms = int(time.time() * 1000)
        return now_ms >= self._tokens.expires_at_ms - 60_000

    async def refresh_if_needed(self) -> bool:
        """Refresh tokens if near expiry. Returns True if refreshed."""
        if not self.needs_refresh():
            return False

        if not self._tokens.refresh_token:
            logger.warning("No refresh token available")
            return False

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config.token_url,
                    data={
                        "grant_type": "refresh_token",
                        "client_id": self.config.client_id,
                        "refresh_token": self._tokens.refresh_token,
                    },
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error("Token refresh failed (%d): %s", resp.status, body)
                        return False

                    data = await resp.json()
                    self._tokens.access_token = data.get("access_token", self._tokens.access_token)
                    self._tokens.refresh_token = data.get("refresh_token", self._tokens.refresh_token)
                    self._tokens.id_token = data.get("id_token", self._tokens.id_token)

                    expires_in = data.get("expires_in", 3600)
                    self._tokens.expires_at_ms = int(time.time() * 1000) + expires_in * 1000

                    # Extract email from new id_token
                    self._tokens.email = _extract_email(self._tokens.id_token) or self._tokens.email

                    self.save()
                    logger.info("Tokens refreshed successfully")
                    return True

        except Exception:
            logger.exception("Token refresh failed")
            return False

    async def exchange_initial_tokens(self, token_response: dict) -> None:
        """Process the initial OAuth token response: extract tokens, exchange for API key, save."""
        self._tokens.access_token = token_response.get("access_token", "")
        self._tokens.refresh_token = token_response.get("refresh_token", "")
        self._tokens.id_token = token_response.get("id_token", "")

        expires_in = token_response.get("expires_in", 3600)
        self._tokens.expires_at_ms = int(time.time() * 1000) + expires_in * 1000

        # Extract email from id_token
        self._tokens.email = _extract_email(self._tokens.id_token) or ""

        self.save()

    def clear(self) -> None:
        """Clear all tokens (logout)."""
        self._tokens = TokenData()
        if _TOKEN_FILE.exists():
            _TOKEN_FILE.unlink()
            logger.info("OAuth tokens deleted")

    def to_status_dict(self) -> dict:
        """Return safe status info (never expose raw tokens)."""
        return {
            "logged_in": self.has_tokens(),
            "email": self._tokens.email,
            "expires_at_ms": self._tokens.expires_at_ms,
        }


def _decode_jwt_payload(id_token: str) -> dict | None:
    """Decode JWT payload without signature verification."""
    if not id_token:
        return None
    try:
        import base64

        parts = id_token.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1]
        payload += "=" * (4 - len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception:
        return None


def _extract_org_id(id_token: str) -> str | None:
    """Extract organization_id from JWT id_token (nested under https://api.openai.com/auth)."""
    data = _decode_jwt_payload(id_token)
    if not data:
        return None
    auth_claims = data.get("https://api.openai.com/auth", {})
    orgs = auth_claims.get("organizations", [])
    if orgs:
        # Use the default org, or first one
        for org in orgs:
            if org.get("is_default"):
                return org.get("id")
        return orgs[0].get("id")
    return None


def _extract_email(id_token: str) -> str | None:
    """Extract email from JWT id_token payload."""
    data = _decode_jwt_payload(id_token)
    return data.get("email") if data else None


def _extract_chatgpt_account_id(id_token: str) -> str | None:
    """Extract chatgpt_account_id from JWT id_token (under https://api.openai.com/auth)."""
    data = _decode_jwt_payload(id_token)
    if not data:
        return None
    auth_claims = data.get("https://api.openai.com/auth", {})
    return auth_claims.get("chatgpt_account_id")
