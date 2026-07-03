import json
import os
import secrets
import time
import traceback
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from backend.config import Settings
from schemas.youtube_oauth_schema import YouTubeChannelInfo
from services.google_oauth_service import GoogleOAuthConfigurationError
from services.utils.logging import get_rotating_logger

youtube_oauth_logger = get_rotating_logger("youtube_oauth", "youtube_oauth.log")

YOUTUBE_OAUTH_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

GOOGLE_SCOPE_ALIASES = {
    "email": "https://www.googleapis.com/auth/userinfo.email",
    "profile": "https://www.googleapis.com/auth/userinfo.profile",
}


class YouTubeOAuthScopeError(Exception):
    """Raised when Google does not grant the required YouTube scopes."""


class YouTubeOAuthTokenError(Exception):
    """Raised when required OAuth token fields are missing or cannot be persisted."""


class YouTubeOAuthService:
    """Manage a single local YouTube channel OAuth connection."""

    authorization_url = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url = "https://oauth2.googleapis.com/token"
    channels_url = "https://www.googleapis.com/youtube/v3/channels"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.connection_path = Path(settings.youtube_oauth_connection_file)

    def build_authorization_url(self, redirect_uri: str) -> tuple[str, str]:
        """Create a YouTube OAuth authorization URL and CSRF state."""
        self._ensure_configured()
        state = secrets.token_urlsafe(32)
        params = {
            "client_id": self.settings.google_oauth_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(YOUTUBE_OAUTH_SCOPES),
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
        }
        youtube_oauth_logger.info("YouTube OAuth started redirect_uri=%s", redirect_uri)
        return f"{self.authorization_url}?{urlencode(params)}", state

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
        granted_scope: str | None = None,
    ) -> dict[str, Any]:
        """Exchange an OAuth authorization code for YouTube-capable tokens."""
        started = time.perf_counter()
        youtube_oauth_logger.info("ENTER exchange_code")
        self._ensure_configured()
        try:
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
                token = self._with_expiry(response.json())
            youtube_oauth_logger.info(
                "exchange_code token keys=%s has_access=%s has_refresh=%s expires_at=%s scope_present=%s",
                sorted(token.keys()),
                bool(token.get("access_token")),
                bool(token.get("refresh_token")),
                token.get("expires_at"),
                bool(token.get("scope")),
            )
            self.validate_required_scopes(token, granted_scope=granted_scope)
            self.validate_token_payload(token)
            youtube_oauth_logger.info("EXIT exchange_code elapsed_ms=%.2f", self._elapsed_ms(started))
            return token
        except Exception as exc:
            self._log_exception("exchange_code", exc, started)
            raise

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh the stored YouTube access token."""
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

    async def fetch_channel_info(self, access_token: str) -> YouTubeChannelInfo:
        """Retrieve the authenticated user's primary YouTube channel."""
        started = time.perf_counter()
        youtube_oauth_logger.info("ENTER fetch_channel_info")
        try:
            youtube_oauth_logger.info("fetch_channel_info before_http_request url=%s access_token_present=%s", self.channels_url, bool(access_token))
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(
                    self.channels_url,
                    params={"part": "snippet,statistics", "mine": "true"},
                    headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                )
                youtube_oauth_logger.info("fetch_channel_info after_http_response status=%s", response.status_code)
                data = response.json()
                youtube_oauth_logger.info("fetch_channel_info returned_json=%s", data)
                response.raise_for_status()
            items = data.get("items") or []
            youtube_oauth_logger.info("fetch_channel_info items_count=%s", len(items))
            if not items:
                youtube_oauth_logger.info("fetch_channel_info empty_payload=%s", data)
                raise ValueError("No YouTube channel was returned for this account")
            channel = self._channel_from_api(items[0])
            youtube_oauth_logger.info("fetch_channel_info parsed_channel=%s", channel.model_dump())
            youtube_oauth_logger.info("EXIT fetch_channel_info elapsed_ms=%.2f", self._elapsed_ms(started))
            return channel
        except Exception as exc:
            self._log_exception("fetch_channel_info", exc, started)
            raise

    async def connect(
        self,
        code: str,
        redirect_uri: str,
        granted_scope: str | None = None,
    ) -> YouTubeChannelInfo:
        """Exchange a code, retrieve channel details, and persist the connection."""
        started = time.perf_counter()
        youtube_oauth_logger.info("ENTER connect")
        try:
            token = await self.exchange_code(
                code=code,
                redirect_uri=redirect_uri,
                granted_scope=granted_scope,
            )
            channel = await self.fetch_channel_info(str(token.get("access_token", "")))
            self.save_connection(token=token, channel=channel, granted_scope=granted_scope)
            self.save_token_file(token=token, granted_scope=granted_scope)
            youtube_oauth_logger.info("Connected YouTube channel_id=%s name=%s", channel.channel_id, channel.channel_name)
            youtube_oauth_logger.info("EXIT connect elapsed_ms=%.2f", self._elapsed_ms(started))
            return channel
        except Exception as exc:
            self._log_exception("connect", exc, started)
            raise

    async def status(self) -> tuple[bool, YouTubeChannelInfo | None, bool, str | None]:
        """Return connection status, refreshing tokens when possible and failing soft."""
        try:
            youtube_oauth_logger.info("TRACE status start connection_path=%s", self.connection_path.resolve())
            connection = self.load_connection()
            youtube_oauth_logger.info("TRACE status load_connection keys=%s", sorted(connection.keys()) if connection else [])
            if not connection:
                youtube_oauth_logger.info("TRACE status returning disconnected reason=empty_connection")
                return False, None, False, None
            if not self.validate_required_scopes(connection, raise_on_error=False):
                youtube_oauth_logger.info("TRACE status returning disconnected reason=missing_scopes")
                return False, None, False, "missing_scopes"
            if self.is_expired(connection):
                youtube_oauth_logger.info("TRACE status token expired refresh_token_present=%s", bool(connection.get("refresh_token")))
                refresh_token = connection.get("refresh_token")
                if not refresh_token:
                    youtube_oauth_logger.info("TRACE status returning disconnected reason=missing_refresh_token")
                    return False, None, True, "missing_refresh_token"
                refreshed = await self.refresh_access_token(str(refresh_token))
                connection.update(
                    {
                        "access_token": refreshed.get("access_token"),
                        "expires_at": refreshed.get("expires_at"),
                        "token_type": refreshed.get("token_type", connection.get("token_type", "Bearer")),
                    }
                )
                self._write_connection(connection)
                self.save_token_file(token=connection)
                youtube_oauth_logger.info("YouTube OAuth token refreshed channel_id=%s", connection.get("channel", {}).get("channel_id"))
            youtube_oauth_logger.info("TRACE status returning connected channel=%s", connection.get("channel"))
            return True, YouTubeChannelInfo(**connection["channel"]), True, None
        except Exception as exc:
            youtube_oauth_logger.exception("YouTube OAuth status failed")
            return False, None, False, str(exc)

    def save_connection(
        self,
        token: dict[str, Any],
        channel: YouTubeChannelInfo,
        granted_scope: str | None = None,
    ) -> None:
        """Persist the minimum channel and token data required for one connection."""
        self.validate_token_payload(token)
        payload = {
            "channel": channel.model_dump(),
            "refresh_token": token.get("refresh_token"),
            "access_token": token.get("access_token"),
            "expires_at": token.get("expires_at"),
            "token_type": token.get("token_type", "Bearer"),
            "scope": self.effective_scope(token, granted_scope),
        }
        self._write_verified_json(self.connection_path, payload, "save_connection")

    def save_token_file(self, token: dict[str, Any], granted_scope: str | None = None) -> None:
        """Persist a local token file for upload services and operational verification."""
        self.validate_token_payload(token)
        payload = {
            "token": token.get("access_token"),
            "refresh_token": token.get("refresh_token"),
            "token_uri": self.token_url,
            "client_id": self.settings.google_oauth_client_id,
            "client_secret": self.settings.google_oauth_client_secret,
            "scopes": sorted(set(self.effective_scope(token, granted_scope).split())),
            "expiry": token.get("expires_at"),
        }
        path = Path(self.settings.youtube_token_file)
        try:
            self._write_verified_json(path, payload, "save_token_file")
        except Exception as exc:
            raise YouTubeOAuthTokenError(f"Failed to persist YouTube token file: {path}") from exc
        if not path.exists():
            raise YouTubeOAuthTokenError(f"YouTube token file was not created: {path}")

    def load_connection(self) -> dict[str, Any]:
        """Load the persisted YouTube connection."""
        if not self.connection_path.exists():
            return {}
        try:
            data = json.loads(self.connection_path.read_text(encoding="utf-8"))
        except Exception:
            youtube_oauth_logger.exception("Failed to load YouTube connection file")
            return {}
        return data if isinstance(data, dict) else {}

    def disconnect(self) -> None:
        """Remove the local YouTube connection."""
        try:
            for path in (self.connection_path, Path(self.settings.youtube_token_file)):
                if path.exists():
                    path.unlink()
            youtube_oauth_logger.info("Disconnected YouTube channel")
        except Exception:
            youtube_oauth_logger.exception("Failed to disconnect YouTube channel")

    def validate_required_scopes(
        self,
        token: dict[str, Any],
        raise_on_error: bool = True,
        granted_scope: str | None = None,
    ) -> bool:
        """Validate that all required YouTube OAuth scopes were granted."""
        required = self.normalize_scopes(YOUTUBE_OAUTH_SCOPES)
        granted = self.normalize_scopes(self.effective_scope(token, granted_scope).split())
        missing = sorted(required - granted)
        youtube_oauth_logger.info("Required scopes: %s", sorted(required))
        youtube_oauth_logger.info("Granted scopes: %s", sorted(granted))
        youtube_oauth_logger.info("Missing scopes: %s", missing)
        if missing:
            if raise_on_error:
                raise YouTubeOAuthScopeError(f"Missing required YouTube scopes: {', '.join(missing)}")
            return False
        return True

    def effective_scope(self, token: dict[str, Any], granted_scope: str | None = None) -> str:
        """Return token scope, falling back to callback granted scope without mutating token."""
        return str(token.get("scope") or granted_scope or "")

    def normalize_scopes(self, scopes: list[str] | tuple[str, ...]) -> set[str]:
        """Normalize official Google OAuth scope aliases before validation."""
        return {GOOGLE_SCOPE_ALIASES.get(scope, scope) for scope in scopes if scope}

    def validate_token_payload(self, token: dict[str, Any]) -> None:
        """Ensure required OAuth token fields exist before persistence."""
        missing = [
            name
            for name in ("access_token", "refresh_token", "expires_at")
            if not token.get(name)
        ]
        if missing:
            raise YouTubeOAuthTokenError(f"Missing required YouTube token fields: {', '.join(missing)}")

    def is_expired(self, connection: dict[str, Any]) -> bool:
        """Return true when the stored access token is near expiry."""
        expires_at = connection.get("expires_at")
        return isinstance(expires_at, (int, float)) and expires_at <= time.time() + 60

    def _write_connection(self, payload: dict[str, Any]) -> None:
        self._write_json_atomic(self.connection_path, payload)

    def _write_json_atomic(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temp_path, path)

    def _write_verified_json(self, path: Path, payload: dict[str, Any], label: str) -> None:
        started = time.perf_counter()
        youtube_oauth_logger.info("ENTER %s", label)
        try:
            absolute_path = path.resolve()
            parent = path.parent
            parent.mkdir(parents=True, exist_ok=True)
            parent_exists = parent.exists()
            parent_writable = os.access(parent, os.W_OK)
            serialized = json.dumps(payload, indent=2)
            exists_before = path.exists()
            youtube_oauth_logger.info(
                "%s absolute_filename=%s parent_exists=%s parent_writable=%s json_length=%s exists_before=%s",
                label,
                absolute_path,
                parent_exists,
                parent_writable,
                len(serialized),
                exists_before,
            )
            self._write_json_atomic(path, payload)
            exists_after = path.exists()
            file_size = path.stat().st_size if exists_after else 0
            raw = path.read_text(encoding="utf-8") if exists_after else ""
            parsed = json.loads(raw) if raw else {}
            youtube_oauth_logger.info(
                "%s exists_after=%s file_size=%s readback_json_length=%s parsed_equals_original=%s",
                label,
                exists_after,
                file_size,
                len(raw),
                parsed == payload,
            )
            if parsed != payload:
                raise YouTubeOAuthTokenError(f"{label} readback mismatch for {path}")
            youtube_oauth_logger.info("EXIT %s elapsed_ms=%.2f", label, self._elapsed_ms(started))
        except Exception as exc:
            self._log_exception(label, exc, started)
            raise

    def _with_expiry(self, token: dict[str, Any]) -> dict[str, Any]:
        expires_in = token.get("expires_in")
        if isinstance(expires_in, int):
            token["expires_at"] = time.time() + expires_in
        return token

    def _elapsed_ms(self, started: float) -> float:
        return (time.perf_counter() - started) * 1000

    def _log_exception(self, label: str, exc: Exception, started: float) -> None:
        youtube_oauth_logger.error(
            "EXCEPTION %s elapsed_ms=%.2f class=%s message=%s traceback=%s",
            label,
            self._elapsed_ms(started),
            exc.__class__.__name__,
            str(exc),
            traceback.format_exc(),
        )

    def _channel_from_api(self, item: dict[str, Any]) -> YouTubeChannelInfo:
        snippet = item.get("snippet") or {}
        statistics = item.get("statistics") or {}
        thumbnails = snippet.get("thumbnails") or {}
        thumbnail = (
            thumbnails.get("high", {}).get("url")
            or thumbnails.get("medium", {}).get("url")
            or thumbnails.get("default", {}).get("url")
            or ""
        )
        return YouTubeChannelInfo(
            channel_id=str(item.get("id", "")),
            channel_name=str(snippet.get("title", "")),
            channel_thumbnail=str(thumbnail),
            subscriber_count=int(statistics.get("subscriberCount") or 0),
            video_count=int(statistics.get("videoCount") or 0),
            country=str(snippet.get("country", "")),
            default_language=str(snippet.get("defaultLanguage") or snippet.get("defaultAudioLanguage") or ""),
        )

    def _ensure_configured(self) -> None:
        if not self.settings.google_oauth_client_id or not self.settings.google_oauth_client_secret:
            raise GoogleOAuthConfigurationError("Google OAuth credentials are not configured")
