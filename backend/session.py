import base64
import hashlib
import hmac
import json
from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send


class SignedCookieSessionMiddleware:
    """Minimal signed-cookie session middleware using only the standard library."""

    def __init__(
        self,
        app: ASGIApp,
        secret_key: str,
        cookie_name: str = "social_media_ai_session",
        same_site: str = "lax",
        https_only: bool = False,
    ) -> None:
        self.app = app
        self.secret_key = secret_key.encode("utf-8")
        self.cookie_name = cookie_name
        self.same_site = same_site
        self.https_only = https_only

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        scope["session"] = self._load_session(request.cookies.get(self.cookie_name))

        async def send_wrapper(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                session = scope.get("session", {})
                response = Response()
                if isinstance(session, dict) and session:
                    response.set_cookie(
                        self.cookie_name,
                        self._dump_session(session),
                        httponly=True,
                        samesite=self.same_site,
                        secure=self.https_only,
                    )
                else:
                    response.delete_cookie(self.cookie_name)
                headers.extend(
                    (name, value)
                    for name, value in response.raw_headers
                    if name.lower() == b"set-cookie"
                )
            await send(message)

        await self.app(scope, receive, send_wrapper)

    def _load_session(self, raw_cookie: str | None) -> dict[str, Any]:
        if not raw_cookie or "." not in raw_cookie:
            return {}
        payload, signature = raw_cookie.rsplit(".", 1)
        expected = self._sign(payload)
        if not hmac.compare_digest(signature, expected):
            return {}
        try:
            data = base64.urlsafe_b64decode(payload.encode("ascii"))
            parsed = json.loads(data.decode("utf-8"))
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _dump_session(self, session: dict[str, Any]) -> str:
        data = json.dumps(session, separators=(",", ":"), default=str).encode("utf-8")
        payload = base64.urlsafe_b64encode(data).decode("ascii")
        return f"{payload}.{self._sign(payload)}"

    def _sign(self, payload: str) -> str:
        return hmac.new(self.secret_key, payload.encode("ascii"), hashlib.sha256).hexdigest()
