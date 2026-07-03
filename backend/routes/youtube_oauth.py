import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from backend.config import Settings, get_settings
from schemas.youtube_oauth_schema import YouTubeStatusResponse
from services.google_oauth_service import GoogleOAuthConfigurationError, GoogleOAuthStateError
from services.youtube_oauth_service import YouTubeOAuthScopeError, YouTubeOAuthService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/youtube", tags=["youtube-oauth"])


def get_youtube_oauth_service(settings: Settings = Depends(get_settings)) -> YouTubeOAuthService:
    """Build the YouTube OAuth service for dependency injection."""
    return YouTubeOAuthService(settings=settings)


def youtube_callback_redirect_uri(request: Request, settings: Settings) -> str:
    """Return configured YouTube callback URI or infer it from the current request."""
    return settings.youtube_oauth_redirect_uri or str(request.url_for("youtube_callback"))


@router.get("/connect")
def youtube_connect(
    request: Request,
    settings: Settings = Depends(get_settings),
    youtube_oauth_service: YouTubeOAuthService = Depends(get_youtube_oauth_service),
) -> RedirectResponse:
    """Start YouTube OAuth connection for one local channel."""
    try:
        url, state = youtube_oauth_service.build_authorization_url(
            youtube_callback_redirect_uri(request, settings)
        )
        request.session["youtube_oauth_state"] = state
        return RedirectResponse(url)
    except GoogleOAuthConfigurationError as exc:
        logger.warning("YouTube OAuth connect unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured",
        ) from exc
    except Exception as exc:
        logger.exception("YouTube OAuth connect failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="YouTube OAuth connect failed",
        ) from exc


@router.get("/callback", name="youtube_callback")
async def youtube_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    scope: str | None = None,
    error: str | None = None,
    settings: Settings = Depends(get_settings),
    youtube_oauth_service: YouTubeOAuthService = Depends(get_youtube_oauth_service),
) -> RedirectResponse:
    """Complete YouTube OAuth connection and persist channel state."""
    if error:
        logger.warning("YouTube OAuth callback returned error=%s", error)
        return RedirectResponse("/ui?youtube=error", status_code=status.HTTP_302_FOUND)
    try:
        expected_state = request.session.get("youtube_oauth_state")
        if not code or not state or state != expected_state:
            raise GoogleOAuthStateError("Invalid YouTube OAuth state")
        await youtube_oauth_service.connect(
            code=code,
            redirect_uri=youtube_callback_redirect_uri(request, settings),
            granted_scope=scope,
        )
        request.session.pop("youtube_oauth_state", None)
        return RedirectResponse("/ui?youtube=connected", status_code=status.HTTP_302_FOUND)
    except GoogleOAuthStateError as exc:
        logger.warning("YouTube OAuth callback state failure: %s", exc)
        request.session.pop("youtube_oauth_state", None)
        return RedirectResponse("/ui?youtube=invalid_state", status_code=status.HTTP_302_FOUND)
    except YouTubeOAuthScopeError:
        logger.exception("YouTube OAuth missing required scopes")
        request.session.pop("youtube_oauth_state", None)
        return RedirectResponse("/ui?youtube=missing_scopes", status_code=status.HTTP_302_FOUND)
    except Exception:
        logger.exception("YouTube OAuth callback failed")
        request.session.pop("youtube_oauth_state", None)
        raise


@router.get("/status", response_model=YouTubeStatusResponse)
async def youtube_status(
    youtube_oauth_service: YouTubeOAuthService = Depends(get_youtube_oauth_service),
) -> YouTubeStatusResponse:
    """Return the current local YouTube channel connection status."""
    connected, channel, scopes_valid, error = await youtube_oauth_service.status()
    return YouTubeStatusResponse(
        connected=connected,
        channel=channel,
        scopes_valid=scopes_valid,
        error=error,
    )


@router.post("/disconnect")
def youtube_disconnect(
    youtube_oauth_service: YouTubeOAuthService = Depends(get_youtube_oauth_service),
) -> dict[str, bool]:
    """Remove the local YouTube channel connection."""
    youtube_oauth_service.disconnect()
    return {"ok": True}
