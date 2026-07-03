from types import SimpleNamespace

import pytest

from backend.config import Settings
from platforms.youtube import YouTubePublisherAdapter
from services.publisher import PublishMetadata, PublishRequest, PublisherService
from services.youtube_service import YouTubeUploadResult


class FakeYouTubeService:
    def __init__(self) -> None:
        self.upload_request: dict[str, object] | None = None
        self.validate_called = False

    def validate_credentials(self) -> bool:
        self.validate_called = True
        return True

    def upload_video(self, **kwargs):
        self.upload_request = kwargs
        return YouTubeUploadResult(
            youtube_video_id="yt-123",
            youtube_url="https://www.youtube.com/watch?v=yt-123",
            processing_status="processing",
            progress=100,
        )


class FakeYouTubeOAuthService:
    def __init__(self) -> None:
        self.disconnect_called = False
        self.status_called = False

    async def status(self):
        self.status_called = True
        return (
            True,
            SimpleNamespace(
                channel_id="UC123",
                channel_name="Test Channel",
                channel_thumbnail="https://example.test/thumb.jpg",
                subscriber_count=10,
                video_count=3,
                country="US",
                default_language="en",
            ),
            True,
            None,
        )

    def disconnect(self) -> None:
        self.disconnect_called = True


@pytest.mark.anyio
async def test_youtube_adapter_registration_and_publish_delegation() -> None:
    youtube_service = FakeYouTubeService()
    oauth_service = FakeYouTubeOAuthService()
    adapter = YouTubePublisherAdapter(
        youtube_service=youtube_service,
        oauth_service=oauth_service,
        settings=Settings(GOOGLE_OAUTH_CLIENT_ID="client", GOOGLE_OAUTH_CLIENT_SECRET="secret"),
    )
    publisher = PublisherService()
    publisher.register_adapter(adapter)

    request = PublishRequest(
        video_path="storage/videos/video_1.mp4",
        thumbnail_path="storage/thumbnails/thumb_1.jpg",
        metadata=PublishMetadata(
            title="Title",
            description="Description",
            tags=["AI", "Shorts"],
            category="22",
            privacy_status="private",
        ),
    )
    result = await publisher.publish("youtube", request)
    channel = await adapter.connect()
    valid = await publisher.validate("YouTube")
    await publisher.disconnect("YouTube")

    assert publisher.registry.list_platforms() == ["YouTube"]
    assert result.success is True
    assert result.platform == "YouTube"
    assert result.platform_video_id == "yt-123"
    assert result.processing_status == "processing"
    assert youtube_service.upload_request == {
        "video_path": "storage/videos/video_1.mp4",
        "title": "Title",
        "description": "Description",
        "tags": ["AI", "Shorts"],
        "privacy_status": "private",
        "thumbnail_path": "storage/thumbnails/thumb_1.jpg",
        "category_id": "22",
        "publish_at": None,
    }
    assert channel.channel_id == "UC123"
    assert valid is True
    assert youtube_service.validate_called is True
    assert oauth_service.disconnect_called is True
