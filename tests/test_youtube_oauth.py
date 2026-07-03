import time
import asyncio
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.config import Settings, get_settings
from backend.main import app
from backend.routes.youtube_oauth import get_youtube_oauth_service
from schemas.youtube_oauth_schema import YouTubeChannelInfo
from services.youtube_oauth_service import YOUTUBE_OAUTH_SCOPES, YouTubeOAuthScopeError, YouTubeOAuthService


class FakeYouTubeOAuthService:
    def __init__(self, *, missing_scopes: bool = False, refresh_fails: bool = False) -> None:
        self.missing_scopes = missing_scopes
        self.refresh_fails = refresh_fails
        self.connected = False
        self.refresh_called = False
        self.disconnected = False
        self.channel = YouTubeChannelInfo(
            channel_id="UC123",
            channel_name="Creator Channel",
            channel_thumbnail="https://example.com/channel.jpg",
            subscriber_count=1200,
            video_count=42,
            country="US",
            default_language="en",
        )

    def build_authorization_url(self, redirect_uri: str) -> tuple[str, str]:
        return "https://accounts.google.com/o/oauth2/v2/auth?scope=youtube", "youtube-state"

    async def connect(
        self,
        code: str,
        redirect_uri: str,
        granted_scope: str | None = None,
    ) -> YouTubeChannelInfo:
        if self.missing_scopes:
            raise YouTubeOAuthScopeError("missing scopes")
        self.connected = True
        return self.channel

    async def status(self) -> tuple[bool, YouTubeChannelInfo | None, bool, str | None]:
        if self.refresh_fails:
            return False, None, False, "refresh failed"
        return self.connected, self.channel if self.connected else None, self.connected, None

    def disconnect(self) -> None:
        self.connected = False
        self.disconnected = True


def override_settings(tmp_path: Path | None = None) -> Settings:
    base_path = tmp_path or Path("storage/uploads")
    return Settings(
        GOOGLE_OAUTH_CLIENT_ID="client-id",
        GOOGLE_OAUTH_CLIENT_SECRET="client-secret",
        YOUTUBE_OAUTH_REDIRECT_URI="http://testserver/youtube/callback",
        YOUTUBE_OAUTH_CONNECTION_FILE=str(base_path / "youtube_test_connection.json"),
        YOUTUBE_TOKEN_FILE=str(base_path / "youtube_token.json"),
    )


def test_youtube_oauth_redirect() -> None:
    fake = FakeYouTubeOAuthService()
    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_youtube_oauth_service] = lambda: fake
    try:
        with TestClient(app) as client:
            response = client.get("/youtube/connect", follow_redirects=False)

        assert response.status_code == 307
        assert response.headers["location"].startswith("https://accounts.google.com")
    finally:
        app.dependency_overrides.clear()


def test_youtube_callback_connects_channel_and_status_returns_channel() -> None:
    fake = FakeYouTubeOAuthService()
    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_youtube_oauth_service] = lambda: fake
    try:
        with TestClient(app) as client:
            client.get("/youtube/connect", follow_redirects=False)
            callback = client.get("/youtube/callback?code=abc&state=youtube-state", follow_redirects=False)
            status = client.get("/youtube/status")

        assert callback.status_code == 302
        assert callback.headers["location"] == "/ui?youtube=connected"
        assert status.json()["connected"] is True
        assert status.json()["channel"]["channel_id"] == "UC123"
    finally:
        app.dependency_overrides.clear()


def test_youtube_disconnect() -> None:
    fake = FakeYouTubeOAuthService()
    fake.connected = True
    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_youtube_oauth_service] = lambda: fake
    try:
        with TestClient(app) as client:
            response = client.post("/youtube/disconnect")
            status = client.get("/youtube/status")

        assert response.json() == {"ok": True}
        assert fake.disconnected is True
        assert status.json()["connected"] is False
    finally:
        app.dependency_overrides.clear()


def test_youtube_service_disconnect_removes_connection_and_token_files(tmp_path: Path) -> None:
    service = YouTubeOAuthService(settings=override_settings(tmp_path))
    service.save_connection(
        token={
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_at": time.time() + 3600,
            "scope": " ".join(YOUTUBE_OAUTH_SCOPES),
        },
        channel=YouTubeChannelInfo(channel_id="UC123", channel_name="Creator Channel"),
    )
    service.save_token_file(
        token={
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_at": time.time() + 3600,
            "scope": " ".join(YOUTUBE_OAUTH_SCOPES),
        }
    )

    service.disconnect()

    assert not (tmp_path / "youtube_test_connection.json").exists()
    assert not (tmp_path / "youtube_token.json").exists()


def test_youtube_missing_scopes_redirects_with_error() -> None:
    fake = FakeYouTubeOAuthService(missing_scopes=True)
    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_youtube_oauth_service] = lambda: fake
    try:
        with TestClient(app) as client:
            client.get("/youtube/connect", follow_redirects=False)
            response = client.get("/youtube/callback?code=abc&state=youtube-state", follow_redirects=False)

        assert response.status_code == 302
        assert response.headers["location"] == "/ui?youtube=missing_scopes"
    finally:
        app.dependency_overrides.clear()


def test_youtube_status_fail_soft_for_invalid_credentials() -> None:
    fake = FakeYouTubeOAuthService(refresh_fails=True)
    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_youtube_oauth_service] = lambda: fake
    try:
        with TestClient(app) as client:
            response = client.get("/youtube/status")

        assert response.status_code == 200
        assert response.json()["connected"] is False
        assert response.json()["error"] == "refresh failed"
    finally:
        app.dependency_overrides.clear()


def test_youtube_service_refreshes_expired_token(tmp_path: Path, monkeypatch) -> None:
    service = YouTubeOAuthService(settings=override_settings(tmp_path))
    service.save_connection(
        token={
            "access_token": "old-token",
            "refresh_token": "refresh-token",
            "expires_at": time.time() - 10,
            "scope": " ".join(YOUTUBE_OAUTH_SCOPES),
        },
        channel=YouTubeChannelInfo(channel_id="UC123", channel_name="Creator Channel"),
    )

    async def fake_refresh(refresh_token: str) -> dict[str, Any]:
        return {"access_token": "new-token", "expires_at": time.time() + 3600, "token_type": "Bearer"}

    monkeypatch.setattr(service, "refresh_access_token", fake_refresh)

    connected, channel, scopes_valid, error = asyncio.run(service.status())

    saved = service.load_connection()
    saved_token = (tmp_path / "youtube_token.json").read_text(encoding="utf-8")
    assert connected is True
    assert channel is not None
    assert scopes_valid is True
    assert error is None
    assert saved["access_token"] == "new-token"
    assert "new-token" in saved_token


def test_youtube_status_fails_soft_for_invalid_refresh_token(tmp_path: Path, monkeypatch) -> None:
    service = YouTubeOAuthService(settings=override_settings(tmp_path))
    service.save_connection(
        token={
            "access_token": "old-token",
            "refresh_token": "bad-refresh-token",
            "expires_at": time.time() - 10,
            "scope": " ".join(YOUTUBE_OAUTH_SCOPES),
        },
        channel=YouTubeChannelInfo(channel_id="UC123", channel_name="Creator Channel"),
    )

    async def fake_refresh(refresh_token: str) -> dict[str, Any]:
        raise RuntimeError("invalid_grant")

    monkeypatch.setattr(service, "refresh_access_token", fake_refresh)

    connected, channel, scopes_valid, error = asyncio.run(service.status())

    assert connected is False
    assert channel is None
    assert scopes_valid is False
    assert "invalid_grant" in str(error)


def test_youtube_service_validates_missing_scopes(tmp_path: Path) -> None:
    service = YouTubeOAuthService(settings=override_settings(tmp_path))

    assert service.validate_required_scopes({"scope": "openid email"}, raise_on_error=False) is False


def test_youtube_service_accepts_canonical_userinfo_scopes(tmp_path: Path) -> None:
    service = YouTubeOAuthService(settings=override_settings(tmp_path))
    granted = (
        "openid "
        "https://www.googleapis.com/auth/userinfo.email "
        "https://www.googleapis.com/auth/userinfo.profile "
        "https://www.googleapis.com/auth/youtube.upload "
        "https://www.googleapis.com/auth/youtube.readonly"
    )

    assert service.validate_required_scopes({"scope": granted}, raise_on_error=False) is True


def test_youtube_service_accepts_required_youtube_upload_scope(tmp_path: Path) -> None:
    service = YouTubeOAuthService(settings=override_settings(tmp_path))
    required = service.normalize_scopes(["https://www.googleapis.com/auth/youtube.upload"])
    granted = service.normalize_scopes(["https://www.googleapis.com/auth/youtube.upload"])

    assert required - granted == set()


def test_youtube_service_accepts_required_youtube_readonly_scope(tmp_path: Path) -> None:
    service = YouTubeOAuthService(settings=override_settings(tmp_path))
    required = service.normalize_scopes(["https://www.googleapis.com/auth/youtube.readonly"])
    granted = service.normalize_scopes(["https://www.googleapis.com/auth/youtube.readonly"])

    assert required - granted == set()


def test_youtube_service_rejects_missing_youtube_upload_scope(tmp_path: Path) -> None:
    service = YouTubeOAuthService(settings=override_settings(tmp_path))
    required = service.normalize_scopes(["https://www.googleapis.com/auth/youtube.upload"])
    granted = service.normalize_scopes([])

    assert required - granted == {"https://www.googleapis.com/auth/youtube.upload"}


def test_youtube_service_rejects_missing_email_scope(tmp_path: Path) -> None:
    service = YouTubeOAuthService(settings=override_settings(tmp_path))
    required = service.normalize_scopes(["email"])
    granted = service.normalize_scopes([])

    assert required - granted == {"https://www.googleapis.com/auth/userinfo.email"}


def token_client(monkeypatch, token_payload: dict[str, object]) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return token_payload

    class FakeAsyncClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, *args, **kwargs) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr("services.youtube_oauth_service.httpx.AsyncClient", FakeAsyncClient)


def complete_token(scope: str | None = None) -> dict[str, object]:
    token: dict[str, object] = {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "expires_in": 3600,
        "token_type": "Bearer",
    }
    if scope is not None:
        token["scope"] = scope
    return token


def test_youtube_service_accepts_token_response_scope(tmp_path: Path, monkeypatch) -> None:
    service = YouTubeOAuthService(settings=override_settings(tmp_path))
    token_client(monkeypatch, complete_token(scope=" ".join(YOUTUBE_OAUTH_SCOPES)))

    token = asyncio.run(
        service.exchange_code(
            code="abc",
            redirect_uri="http://testserver/youtube/callback",
        )
    )

    assert token["scope"] == " ".join(YOUTUBE_OAUTH_SCOPES)


def test_youtube_service_accepts_callback_scope_when_token_scope_is_missing(tmp_path: Path, monkeypatch) -> None:
    service = YouTubeOAuthService(settings=override_settings(tmp_path))
    token_client(monkeypatch, complete_token())

    token = asyncio.run(
        service.exchange_code(
            code="abc",
            redirect_uri="http://testserver/youtube/callback",
            granted_scope=" ".join(YOUTUBE_OAUTH_SCOPES)
            + " https://www.googleapis.com/auth/userinfo.profile"
            + " https://www.googleapis.com/auth/userinfo.email",
        )
    )

    assert "scope" not in token


def test_youtube_connect_with_canonical_userinfo_scopes_persists_and_status_connects(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = YouTubeOAuthService(settings=override_settings(tmp_path))
    token_client(monkeypatch, complete_token())

    async def fake_channel(access_token: str) -> YouTubeChannelInfo:
        return YouTubeChannelInfo(channel_id="UC123", channel_name="Creator Channel")

    monkeypatch.setattr(service, "fetch_channel_info", fake_channel)

    asyncio.run(
        service.connect(
            code="abc",
            redirect_uri="http://testserver/youtube/callback",
            granted_scope=(
                "openid "
                "https://www.googleapis.com/auth/userinfo.email "
                "https://www.googleapis.com/auth/userinfo.profile "
                "https://www.googleapis.com/auth/youtube.upload "
                "https://www.googleapis.com/auth/youtube.readonly"
            ),
        )
    )
    connected, channel, scopes_valid, error = asyncio.run(service.status())

    assert (tmp_path / "youtube_test_connection.json").exists()
    assert connected is True
    assert channel is not None
    assert channel.channel_id == "UC123"
    assert scopes_valid is True
    assert error is None


def test_youtube_service_rejects_callback_scope_missing_upload(tmp_path: Path, monkeypatch) -> None:
    service = YouTubeOAuthService(settings=override_settings(tmp_path))
    token_client(monkeypatch, complete_token())
    scopes = [scope for scope in YOUTUBE_OAUTH_SCOPES if scope != "https://www.googleapis.com/auth/youtube.upload"]

    try:
        asyncio.run(
            service.exchange_code(
                code="abc",
                redirect_uri="http://testserver/youtube/callback",
                granted_scope=" ".join(scopes),
            )
        )
    except YouTubeOAuthScopeError as exc:
        assert "youtube.upload" in str(exc)
    else:
        raise AssertionError("Expected missing youtube.upload scope to fail")


def test_youtube_service_rejects_callback_scope_missing_readonly(tmp_path: Path, monkeypatch) -> None:
    service = YouTubeOAuthService(settings=override_settings(tmp_path))
    token_client(monkeypatch, complete_token())
    scopes = [scope for scope in YOUTUBE_OAUTH_SCOPES if scope != "https://www.googleapis.com/auth/youtube.readonly"]

    try:
        asyncio.run(
            service.exchange_code(
                code="abc",
                redirect_uri="http://testserver/youtube/callback",
                granted_scope=" ".join(scopes),
            )
        )
    except YouTubeOAuthScopeError as exc:
        assert "youtube.readonly" in str(exc)
    else:
        raise AssertionError("Expected missing youtube.readonly scope to fail")


def test_youtube_service_prefers_token_scope_when_callback_scope_is_also_present(tmp_path: Path, monkeypatch) -> None:
    service = YouTubeOAuthService(settings=override_settings(tmp_path))
    token_client(monkeypatch, complete_token(scope=" ".join(YOUTUBE_OAUTH_SCOPES)))

    token = asyncio.run(
        service.exchange_code(
            code="abc",
            redirect_uri="http://testserver/youtube/callback",
            granted_scope="openid email",
        )
    )

    assert token["scope"] == " ".join(YOUTUBE_OAUTH_SCOPES)


def test_youtube_connect_persists_token_file(tmp_path: Path, monkeypatch) -> None:
    service = YouTubeOAuthService(settings=override_settings(tmp_path))
    token_client(monkeypatch, complete_token())

    async def fake_channel(access_token: str) -> YouTubeChannelInfo:
        return YouTubeChannelInfo(channel_id="UC123", channel_name="Creator Channel")

    monkeypatch.setattr(service, "fetch_channel_info", fake_channel)

    asyncio.run(
        service.connect(
            code="abc",
            redirect_uri="http://testserver/youtube/callback",
            granted_scope=" ".join(YOUTUBE_OAUTH_SCOPES),
        )
    )

    token_path = tmp_path / "youtube_token.json"
    connection_path = tmp_path / "youtube_test_connection.json"
    assert token_path.exists()
    assert connection_path.exists()
    saved_token = token_path.read_text(encoding="utf-8")
    assert "refresh-token" in saved_token


def test_youtube_dashboard_bindings() -> None:
    html = Path("frontend/index.html").read_text(encoding="utf-8")
    javascript = Path("frontend/app.js").read_text(encoding="utf-8")

    assert "YouTube Channel" in html
    assert "youtubeConnectionStatus" in html
    assert "youtubeChannelName" in html
    assert "youtubeChannelId" in html
    assert "youtubeSubscribers" in html
    assert "youtubeVideos" in html
    assert "youtubeCountry" in html
    assert "youtubeLanguage" in html
    assert "/youtube/status" in javascript
    assert "/youtube/disconnect" in javascript
