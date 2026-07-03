import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from backend.config import Settings, get_settings
from schemas.auth_schema import AuthStatusResponse, AuthUser
from services.google_oauth_service import (
    GoogleOAuthConfigurationError,
    GoogleOAuthService,
    GoogleOAuthStateError,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def get_google_oauth_service(settings: Settings = Depends(get_settings)) -> GoogleOAuthService:
    """Build the Google OAuth service for route dependency injection."""
    return GoogleOAuthService(settings=settings)


def callback_redirect_uri(request: Request, settings: Settings) -> str:
    """Return the configured callback URI, or infer it from the current request."""
    return settings.google_oauth_redirect_uri or str(request.url_for("auth_callback"))


@router.get("/login")
def auth_login(
    request: Request,
    settings: Settings = Depends(get_settings),
    oauth_service: GoogleOAuthService = Depends(get_google_oauth_service),
) -> RedirectResponse:
    """Start Google OAuth login."""
    try:
        url, state = oauth_service.build_authorization_url(callback_redirect_uri(request, settings))
        request.session["oauth_state"] = state
        return RedirectResponse(url)
    except GoogleOAuthConfigurationError as exc:
        logger.warning("Google OAuth login unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured",
        ) from exc
    except Exception as exc:
        logger.exception("Google OAuth login failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth login failed",
        ) from exc


@router.get("/callback", name="auth_callback")
async def auth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    settings: Settings = Depends(get_settings),
    oauth_service: GoogleOAuthService = Depends(get_google_oauth_service),
) -> RedirectResponse:
    """Complete Google OAuth login and store a signed browser session."""
    if error:
        logger.warning("Google OAuth callback returned error=%s", error)
        return RedirectResponse("/ui?auth=error", status_code=status.HTTP_302_FOUND)
    try:
        expected_state = request.session.get("oauth_state")
        if not code or not state or state != expected_state:
            raise GoogleOAuthStateError("Invalid OAuth state")

        token = await oauth_service.exchange_code(code=code, redirect_uri=callback_redirect_uri(request, settings))
        user = await oauth_service.fetch_userinfo(access_token=str(token.get("access_token", "")))
        request.session.pop("oauth_state", None)
        request.session["auth"] = oauth_service.session_from_token(token=token, user=user)
        return RedirectResponse("/ui?auth=success", status_code=status.HTTP_302_FOUND)
    except GoogleOAuthStateError as exc:
        logger.warning("Google OAuth callback state failure: %s", exc)
        request.session.pop("oauth_state", None)
        return RedirectResponse("/ui?auth=invalid_state", status_code=status.HTTP_302_FOUND)
    except Exception:
        logger.exception("Google OAuth callback failed")
        request.session.pop("oauth_state", None)
        return RedirectResponse("/ui?auth=error", status_code=status.HTTP_302_FOUND)


@router.post("/logout")
def auth_logout(request: Request) -> dict[str, bool]:
    """Clear the authenticated session."""
    request.session.pop("auth", None)
    request.session.pop("oauth_state", None)
    return {"ok": True}


@router.get("/status", response_model=AuthStatusResponse)
async def auth_status(
    request: Request,
    oauth_service: GoogleOAuthService = Depends(get_google_oauth_service),
) -> AuthStatusResponse:
    """Return current authentication status, refreshing the access token when possible."""
    auth_session = request.session.get("auth")
    if not isinstance(auth_session, dict):
        return AuthStatusResponse(authenticated=False)

    try:
        if oauth_service.is_expired(auth_session) and auth_session.get("refresh_token"):
            refreshed = await oauth_service.refresh_access_token(str(auth_session["refresh_token"]))
            auth_session.update(
                {
                    "access_token": refreshed.get("access_token"),
                    "expires_at": refreshed.get("expires_at"),
                    "token_type": refreshed.get("token_type", auth_session.get("token_type", "Bearer")),
                }
            )
            request.session["auth"] = auth_session
        user = auth_session.get("user")
        if not isinstance(user, dict):
            return AuthStatusResponse(authenticated=False)
        return AuthStatusResponse(authenticated=True, user=AuthUser(**user))
    except Exception:
        logger.exception("Auth status check failed")
        return AuthStatusResponse(authenticated=False)


def require_authenticated_user(request: Request) -> dict[str, Any]:
    """Dependency for future routes that require an authenticated Google user."""
    auth_session = request.session.get("auth")
    user = auth_session.get("user") if isinstance(auth_session, dict) else None
    if not isinstance(user, dict):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user
