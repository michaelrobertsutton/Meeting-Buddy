from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import urllib.parse

from aiohttp import web

from backend.auth.oauth import OAuthConfig, TokenManager

logger = logging.getLogger(__name__)

# Success HTML returned to browser after OAuth callback
_SUCCESS_HTML = """<!DOCTYPE html>
<html>
<head><title>Meeting Buddy</title>
<style>
body { font-family: -apple-system, system-ui, sans-serif; display: flex;
       justify-content: center; align-items: center; height: 100vh;
       margin: 0; background: #1a1a2e; color: #e0e0e0; }
.card { text-align: center; padding: 40px; }
h1 { color: #4fc3f7; margin-bottom: 12px; }
p { color: #999; }
</style></head>
<body>
<div class="card">
  <h1>Logged in!</h1>
  <p>You can close this tab and return to Meeting Buddy.</p>
</div>
</body></html>"""

_ERROR_HTML = """<!DOCTYPE html>
<html>
<head><title>Meeting Buddy</title>
<style>
body { font-family: -apple-system, system-ui, sans-serif; display: flex;
       justify-content: center; align-items: center; height: 100vh;
       margin: 0; background: #1a1a2e; color: #e0e0e0; }
.card { text-align: center; padding: 40px; }
h1 { color: #ef5350; margin-bottom: 12px; }
p { color: #999; }
</style></head>
<body>
<div class="card">
  <h1>Login Failed</h1>
  <p>{error}</p>
</div>
</body></html>"""


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class LoginServer:
    """Runs a temporary local HTTP server for the OAuth PKCE callback."""

    def __init__(self, token_manager: TokenManager, config: OAuthConfig | None = None) -> None:
        self._token_manager = token_manager
        self._config = config or OAuthConfig()
        self._code_verifier: str = ""
        self._state: str = ""
        self._login_future: asyncio.Future | None = None
        self._runner: web.AppRunner | None = None

    async def start_login(self) -> str:
        """Start the login flow: spin up callback server, return the auth URL to open."""
        # Generate PKCE values
        self._code_verifier = _base64url(os.urandom(32))
        code_challenge = _base64url(hashlib.sha256(self._code_verifier.encode("ascii")).digest())
        self._state = _base64url(os.urandom(32))

        redirect_uri = f"http://localhost:{self._config.redirect_port}/auth/callback"

        # Build authorization URL
        params = {
            "response_type": "code",
            "client_id": self._config.client_id,
            "redirect_uri": redirect_uri,
            "scope": self._config.scopes,
            "state": self._state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
            "originator": "codex_cli_rs",
            "audience": "https://api.openai.com/v1",
            "prompt": "consent",
        }
        auth_url = self._config.auth_url + "?" + urllib.parse.urlencode(params)

        # Start local HTTP server for callback
        app = web.Application()
        app.router.add_get("/auth/callback", self._handle_callback)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "localhost", self._config.redirect_port)
        await site.start()

        # Create future that callback will resolve
        loop = asyncio.get_event_loop()
        self._login_future = loop.create_future()

        logger.info("Login server listening on localhost:%d", self._config.redirect_port)
        return auth_url

    async def _handle_callback(self, request: web.Request) -> web.Response:
        """Handle the OAuth redirect callback from the browser."""
        error = request.query.get("error")
        if error:
            error_desc = request.query.get("error_description", error)
            logger.error("OAuth callback error: %s", error_desc)
            if self._login_future and not self._login_future.done():
                self._login_future.set_exception(RuntimeError(error_desc))
            # Schedule cleanup
            asyncio.get_event_loop().call_soon(asyncio.ensure_future, self._cleanup())
            return web.Response(
                text=_ERROR_HTML.format(error=error_desc),
                content_type="text/html",
            )

        code = request.query.get("code")
        state = request.query.get("state")

        if state != self._state:
            msg = "State mismatch — possible CSRF"
            logger.error(msg)
            if self._login_future and not self._login_future.done():
                self._login_future.set_exception(RuntimeError(msg))
            asyncio.get_event_loop().call_soon(asyncio.ensure_future, self._cleanup())
            return web.Response(text=_ERROR_HTML.format(error=msg), content_type="text/html")

        if not code:
            msg = "No authorization code received"
            logger.error(msg)
            if self._login_future and not self._login_future.done():
                self._login_future.set_exception(RuntimeError(msg))
            asyncio.get_event_loop().call_soon(asyncio.ensure_future, self._cleanup())
            return web.Response(text=_ERROR_HTML.format(error=msg), content_type="text/html")

        # Exchange code for tokens
        try:
            redirect_uri = f"http://localhost:{self._config.redirect_port}/auth/callback"
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._config.token_url,
                    data={
                        "grant_type": "authorization_code",
                        "client_id": self._config.client_id,
                        "code": code,
                        "redirect_uri": redirect_uri,
                        "code_verifier": self._code_verifier,
                    },
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise RuntimeError(f"Token exchange failed ({resp.status}): {body}")
                    token_data = await resp.json()

            # Process tokens: exchange id_token for API key, save
            await self._token_manager.exchange_initial_tokens(token_data)

            if self._login_future and not self._login_future.done():
                self._login_future.set_result(True)

            logger.info("OAuth login completed successfully")

        except Exception as e:
            logger.exception("OAuth token exchange failed")
            if self._login_future and not self._login_future.done():
                self._login_future.set_exception(e)
            asyncio.get_event_loop().call_soon(asyncio.ensure_future, self._cleanup())
            return web.Response(
                text=_ERROR_HTML.format(error=str(e)),
                content_type="text/html",
            )

        # Schedule cleanup after response is sent
        asyncio.get_event_loop().call_soon(asyncio.ensure_future, self._cleanup())

        return web.Response(text=_SUCCESS_HTML, content_type="text/html")

    async def await_login(self, timeout: float = 120) -> bool:
        """Wait for the OAuth callback to complete. Returns True on success."""
        if not self._login_future:
            raise RuntimeError("Login not started")
        try:
            return await asyncio.wait_for(self._login_future, timeout=timeout)
        except asyncio.TimeoutError as e:
            logger.warning("Login timed out after %ds", timeout)
            raise RuntimeError("Login timed out — try again") from e
        finally:
            await self._cleanup()

    async def _cleanup(self) -> None:
        """Shut down the temporary callback server."""
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
            logger.info("Login callback server stopped")
