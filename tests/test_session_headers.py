from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from backend.session import SignedCookieSessionMiddleware


def test_session_middleware_does_not_add_duplicate_content_length(tmp_path: Path) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<!doctype html><h1>ok</h1>", encoding="utf-8")

    app = FastAPI()
    app.add_middleware(SignedCookieSessionMiddleware, secret_key="test-secret")
    app.mount("/ui", StaticFiles(directory=str(frontend), html=True), name="ui")

    with TestClient(app) as client:
        response = client.get("/ui/")

    content_length_headers = [
        value
        for name, value in response.headers.raw
        if name.lower() == b"content-length"
    ]
    assert response.status_code == 200
    assert len(content_length_headers) == 1
