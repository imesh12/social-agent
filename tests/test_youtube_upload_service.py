import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from googleapiclient.errors import HttpError

from backend.config import Settings
from services.youtube_oauth_service import YOUTUBE_OAUTH_SCOPES
from services.youtube_service import YouTubeService


class FakeProgress:
    def __init__(self, value: float) -> None:
        self.value = value

    def progress(self) -> float:
        return self.value


class FakeUploadRequest:
    def __init__(self, failure: Exception | None = None) -> None:
        self.calls = 0
        self.failure = failure

    def next_chunk(self) -> tuple[FakeProgress, dict[str, str] | None]:
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        if self.calls == 1:
            return FakeProgress(0.45), None
        return FakeProgress(1.0), {"id": "youtube-real-id"}


class FakeExecuteRequest:
    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.payload = payload or {}
        self.executed = False

    def execute(self) -> dict[str, Any]:
        self.executed = True
        return self.payload


class FakeVideosResource:
    def __init__(self, failure: Exception | None = None) -> None:
        self.insert_body: dict[str, Any] | None = None
        self.failure = failure

    def insert(self, part: str, body: dict[str, Any], media_body: Any) -> FakeUploadRequest:
        self.insert_body = body
        return FakeUploadRequest(failure=self.failure)

    def list(self, part: str, id: str) -> FakeExecuteRequest:
        return FakeExecuteRequest(
            {
                "items": [
                    {
                        "processingDetails": {"processingStatus": "processing"},
                        "status": {"uploadStatus": "uploaded"},
                    }
                ]
            }
        )


class FakeThumbnailsResource:
    def __init__(self) -> None:
        self.uploaded_video_id: str | None = None

    def set(self, videoId: str, media_body: Any) -> FakeExecuteRequest:
        self.uploaded_video_id = videoId
        return FakeExecuteRequest({})


class FakeYouTubeClient:
    def __init__(self, failure: Exception | None = None) -> None:
        self.videos_resource = FakeVideosResource(failure=failure)
        self.thumbnails_resource = FakeThumbnailsResource()

    def videos(self) -> FakeVideosResource:
        return self.videos_resource

    def thumbnails(self) -> FakeThumbnailsResource:
        return self.thumbnails_resource


def test_real_youtube_upload_uses_resumable_upload_and_thumbnail(tmp_path: Path) -> None:
    video_path = tmp_path / "video.mp4"
    thumbnail_path = tmp_path / "thumb.jpg"
    video_path.write_bytes(b"fake video")
    thumbnail_path.write_bytes(b"fake jpg")
    client = FakeYouTubeClient()
    service = YouTubeService.__new__(YouTubeService)
    service.settings = Settings()
    service._build_client = lambda: client

    result = YouTubeService.upload_video.__wrapped__(
        service,
        video_path=str(video_path),
        title="Real Upload Title",
        description="Real description",
        tags=["AI", "Shorts"],
        privacy_status="private",
        thumbnail_path=str(thumbnail_path),
        publish_at="2026-07-02T18:00:00Z",
    )

    assert result.youtube_video_id == "youtube-real-id"
    assert result.youtube_url == "https://www.youtube.com/watch?v=youtube-real-id"
    assert result.thumbnail_url == "https://img.youtube.com/vi/youtube-real-id/maxresdefault.jpg"
    assert result.progress == 100
    assert result.processing_status == "processing"
    assert client.thumbnails_resource.uploaded_video_id == "youtube-real-id"
    assert client.videos_resource.insert_body is not None
    assert client.videos_resource.insert_body["snippet"]["title"] == "Real Upload Title"
    assert client.videos_resource.insert_body["status"]["publishAt"] == "2026-07-02T18:00:00Z"


def test_youtube_upload_missing_thumbnail_does_not_fail(tmp_path: Path) -> None:
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake video")
    client = FakeYouTubeClient()
    service = YouTubeService.__new__(YouTubeService)
    service.settings = Settings()
    service._build_client = lambda: client

    result = YouTubeService.upload_video.__wrapped__(
        service,
        video_path=str(video_path),
        thumbnail_path=str(tmp_path / "missing.jpg"),
    )

    assert result.youtube_video_id == "youtube-real-id"
    assert result.thumbnail_url == ""
    assert client.thumbnails_resource.uploaded_video_id is None


def test_youtube_upload_quota_error_is_not_transient(tmp_path: Path) -> None:
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake video")
    error = HttpError(
        resp=type("Resp", (), {"status": 403, "reason": "Forbidden"})(),
        content=b'{"error":{"errors":[{"reason":"quotaExceeded"}]}}',
    )
    client = FakeYouTubeClient(failure=error)
    service = YouTubeService.__new__(YouTubeService)
    service.settings = Settings()
    service._build_client = lambda: client

    try:
        YouTubeService.upload_video.__wrapped__(service, video_path=str(video_path))
    except HttpError as exc:
        assert "quotaExceeded" in service._http_error_body(exc)
        assert service._is_transient_error(exc) is False
    else:
        raise AssertionError("Expected quotaExceeded upload to fail")


def test_youtube_upload_retry_succeeds_after_transient_failure(tmp_path: Path, monkeypatch) -> None:
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake video")
    service = YouTubeService.__new__(YouTubeService)
    service.settings = Settings()
    calls = {"count": 0}

    def fake_build_client() -> FakeYouTubeClient:
        calls["count"] += 1
        if calls["count"] == 1:
            error = HttpError(
                resp=type("Resp", (), {"status": 503, "reason": "Unavailable"})(),
                content=b'{"error":{"errors":[{"reason":"backendError"}]}}',
            )
            return FakeYouTubeClient(failure=error)
        return FakeYouTubeClient()

    monkeypatch.setattr("services.utils.retry.time.sleep", lambda delay: None)
    service._build_client = fake_build_client

    result = service.upload_video(video_path=str(video_path))

    assert result.youtube_video_id == "youtube-real-id"
    assert calls["count"] == 2


def test_youtube_service_refreshes_connected_access_token(tmp_path: Path, monkeypatch) -> None:
    connection_path = tmp_path / "youtube_connection.json"
    connection_path.write_text(
        json.dumps(
            {
                "channel": {"channel_id": "UC123", "channel_name": "Creator"},
                "access_token": "old-token",
                "refresh_token": "refresh-token",
                "expires_at": 1,
                "scope": " ".join(YOUTUBE_OAUTH_SCOPES),
            }
        ),
        encoding="utf-8",
    )
    service = YouTubeService.__new__(YouTubeService)
    service.settings = Settings(
        GOOGLE_OAUTH_CLIENT_ID="client-id",
        GOOGLE_OAUTH_CLIENT_SECRET="client-secret",
        YOUTUBE_OAUTH_CONNECTION_FILE=str(connection_path),
    )

    class FakeCredentials:
        def __init__(self, **kwargs: Any) -> None:
            self.token = kwargs["token"]
            self.refresh_token = kwargs["refresh_token"]
            self.expired = True
            self.valid = False
            self.expiry = None

        def refresh(self, request: Any) -> None:
            self.token = "new-token"
            self.expired = False
            self.valid = True
            self.expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(tzinfo=None)

    monkeypatch.setattr("services.youtube_service.Credentials", FakeCredentials)

    credentials = service._load_credentials()
    saved = json.loads(connection_path.read_text(encoding="utf-8"))

    assert credentials.token == "new-token"
    assert saved["access_token"] == "new-token"
