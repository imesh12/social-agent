import time
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from backend.config import Settings, get_settings
from backend.main import app
from backend.routes.auth import get_google_oauth_service, require_authenticated_user
from backend.session import SignedCookieSessionMiddleware


class FakeGoogleOAuthService:
    def __init__(self, *, expired: bool = False, refresh_fails: bool = False) -> None:
        self.expired = expired
        self.refresh_fails = refresh_fails
        self.refresh_called = False

    def build_authorization_url(self, redirect_uri: str) -> tuple[str, str]:
        return "https://accounts.google.com/o/oauth2/v2/auth?state=state-token", "state-token"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        return {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "token_type": "Bearer",
            "expires_at": time.time() - 10 if self.expired else time.time() + 3600,
        }

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        self.refresh_called = True
        if self.refresh_fails:
            raise RuntimeError("refresh failed")
        return {
            "access_token": "refreshed-token",
            "token_type": "Bearer",
            "expires_at": time.time() + 3600,
        }

    async def fetch_userinfo(self, access_token: str) -> dict[str, str]:
        return {
            "email": "creator@example.com",
            "name": "Creator One",
            "picture": "https://example.com/avatar.jpg",
        }

    def session_from_token(self, token: dict[str, Any], user: dict[str, str]) -> dict[str, Any]:
        return {
            "user": user,
            "access_token": token["access_token"],
            "refresh_token": token["refresh_token"],
            "expires_at": token["expires_at"],
            "token_type": token["token_type"],
        }

    def is_expired(self, auth_session: dict[str, Any]) -> bool:
        return bool(auth_session.get("expires_at", 0) <= time.time() + 60)


def override_settings() -> Settings:
    return Settings(
        GOOGLE_OAUTH_CLIENT_ID="client-id",
        GOOGLE_OAUTH_CLIENT_SECRET="client-secret",
        GOOGLE_OAUTH_REDIRECT_URI="http://testserver/auth/callback",
    )


def test_login_route_redirects_to_google_and_persists_state() -> None:
    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_google_oauth_service] = lambda: FakeGoogleOAuthService()
    try:
        with TestClient(app) as client:
            response = client.get("/auth/login", follow_redirects=False)

            assert response.status_code == 307
            assert response.headers["location"].startswith("https://accounts.google.com")
            assert client.cookies
    finally:
        app.dependency_overrides.clear()


def test_callback_handling_stores_session_and_status_returns_user() -> None:
    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_google_oauth_service] = lambda: FakeGoogleOAuthService()
    try:
        with TestClient(app) as client:
            client.get("/auth/login", follow_redirects=False)
            callback = client.get("/auth/callback?code=abc&state=state-token", follow_redirects=False)
            status = client.get("/auth/status")

        assert callback.status_code == 302
        assert callback.headers["location"] == "/ui?auth=success"
        assert status.json() == {
            "authenticated": True,
            "user": {
                "email": "creator@example.com",
                "name": "Creator One",
                "picture": "https://example.com/avatar.jpg",
            },
        }
    finally:
        app.dependency_overrides.clear()


def test_logout_clears_authenticated_session() -> None:
    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_google_oauth_service] = lambda: FakeGoogleOAuthService()
    try:
        with TestClient(app) as client:
            client.get("/auth/login", follow_redirects=False)
            client.get("/auth/callback?code=abc&state=state-token", follow_redirects=False)
            logout = client.post("/auth/logout")
            status = client.get("/auth/status")

        assert logout.json() == {"ok": True}
        assert status.json() == {"authenticated": False, "user": None}
    finally:
        app.dependency_overrides.clear()


def test_auth_status_refreshes_expired_access_token() -> None:
    fake = FakeGoogleOAuthService(expired=True)
    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_google_oauth_service] = lambda: fake
    try:
        with TestClient(app) as client:
            client.get("/auth/login", follow_redirects=False)
            client.get("/auth/callback?code=abc&state=state-token", follow_redirects=False)
            status = client.get("/auth/status")

        assert status.json()["authenticated"] is True
        assert fake.refresh_called is True
    finally:
        app.dependency_overrides.clear()


def test_auth_status_fails_soft_when_refresh_fails() -> None:
    fake = FakeGoogleOAuthService(expired=True, refresh_fails=True)
    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_google_oauth_service] = lambda: fake
    try:
        with TestClient(app) as client:
            client.get("/auth/login", follow_redirects=False)
            client.get("/auth/callback?code=abc&state=state-token", follow_redirects=False)
            status = client.get("/auth/status")

        assert status.status_code == 200
        assert status.json() == {"authenticated": False, "user": None}
    finally:
        app.dependency_overrides.clear()


def test_login_route_reports_missing_configuration() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        GOOGLE_OAUTH_CLIENT_ID="",
        GOOGLE_OAUTH_CLIENT_SECRET="",
    )
    try:
        with TestClient(app) as client:
            response = client.get("/auth/login", follow_redirects=False)

        assert response.status_code == 503
        assert response.json()["detail"] == "Google OAuth is not configured"
    finally:
        app.dependency_overrides.clear()


def test_protected_endpoint_dependency_requires_session() -> None:
    protected_app = FastAPI()
    protected_app.add_middleware(SignedCookieSessionMiddleware, secret_key="test-secret")

    @protected_app.get("/protected")
    def protected(user: dict[str, Any] = Depends(require_authenticated_user)) -> dict[str, Any]:
        return {"email": user["email"]}

    with TestClient(protected_app) as client:
        response = client.get("/protected")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"
