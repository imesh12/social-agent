import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from backend.config import Settings
from services.utils.logging import get_rotating_logger

auth_logger = get_rotating_logger("auth", "auth.log")


class GoogleOAuthConfigurationError(Exception):
    """Raised when Google OAuth credentials are not configured."""


class GoogleOAuthStateError(Exception):
    """Raised when the callback state does not match the login session."""


class GoogleOAuthService:
    """Small Google OAuth 2.0 Authorization Code Flow wrapper."""

    authorization_url = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url = "https://oauth2.googleapis.com/token"
    userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def build_authorization_url(self, redirect_uri: str) -> tuple[str, str]:
        """Create the Google authorization URL and CSRF state value."""
        self._ensure_configured()
        state = secrets.token_urlsafe(32)
        params = {
            "client_id": self.settings.google_oauth_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self.settings.google_oauth_scopes,
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
        }
        return f"{self.authorization_url}?{urlencode(params)}", state

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        """Exchange an authorization code for Google token data."""
        self._ensure_configured()
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                self.token_url,
                data={
                    "code": code,
                    "client_id": self.settings.google_oauth_client_id,
                    "client_secret": self.settings.google_oauth_client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return self._with_expiry(response.json())

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh an expired Google access token."""
        self._ensure_configured()
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                self.token_url,
                data={
                    "client_id": self.settings.google_oauth_client_id,
                    "client_secret": self.settings.google_oauth_client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return self._with_expiry(response.json())

    async def fetch_userinfo(self, access_token: str) -> dict[str, str]:
        """Fetch the minimal Google profile used by the dashboard."""
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                self.userinfo_url,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
        return {
            "email": str(data.get("email", "")),
            "name": str(data.get("name", "")),
            "picture": str(data.get("picture", "")),
        }

    def session_from_token(self, token: dict[str, Any], user: dict[str, str]) -> dict[str, Any]:
        """Build the minimum signed-cookie session payload."""
        return {
            "user": user,
            "access_token": token.get("access_token"),
            "refresh_token": token.get("refresh_token"),
            "expires_at": token.get("expires_at"),
            "token_type": token.get("token_type", "Bearer"),
        }

    def is_expired(self, auth_session: dict[str, Any]) -> bool:
        """Return true when the access token is near expiry."""
        expires_at = auth_session.get("expires_at")
        return isinstance(expires_at, (int, float)) and expires_at <= time.time() + 60

    def _with_expiry(self, token: dict[str, Any]) -> dict[str, Any]:
        expires_in = token.get("expires_in")
        if isinstance(expires_in, int):
            token["expires_at"] = time.time() + expires_in
        return token

    def _ensure_configured(self) -> None:
        if not self.settings.google_oauth_client_id or not self.settings.google_oauth_client_secret:
            raise GoogleOAuthConfigurationError("Google OAuth credentials are not configured")
