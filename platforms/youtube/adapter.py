from datetime import datetime

from backend.config import Settings, get_settings
from services.publisher.base_adapter import BasePublisherAdapter
from services.publisher.exceptions import AuthenticationError, UploadError
from services.publisher.models import ChannelInfo, PublishRequest, PublishResult
from services.youtube_oauth_service import YouTubeOAuthService
from services.youtube_service import YouTubeService


class YouTubePublisherAdapter(BasePublisherAdapter):
    """Bridge adapter that delegates to the existing YouTube services."""

    def __init__(
        self,
        youtube_service: YouTubeService | None = None,
        oauth_service: YouTubeOAuthService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.youtube_service = youtube_service or YouTubeService()
        self.oauth_service = oauth_service or YouTubeOAuthService(settings=self.settings)

    @property
    def platform_name(self) -> str:
        return "YouTube"

    async def connect(self) -> ChannelInfo:
        """Return the active YouTube channel connection."""
        connected, channel, _scopes_valid, error = await self.oauth_service.status()
        if not connected or channel is None:
            raise AuthenticationError(error or "YouTube channel is not connected")
        return ChannelInfo(
            platform=self.platform_name,
            channel_id=channel.channel_id,
            channel_name=channel.channel_name,
            thumbnail_url=channel.channel_thumbnail,
            subscriber_count=channel.subscriber_count,
            video_count=channel.video_count,
            country=channel.country,
            default_language=channel.default_language,
        )

    async def disconnect(self) -> None:
        """Disconnect the local YouTube channel."""
        self.oauth_service.disconnect()

    async def validate(self) -> bool:
        """Validate existing YouTube upload credentials."""
        return self.youtube_service.validate_credentials()

    async def publish(self, request: PublishRequest) -> PublishResult:
        """Publish through the existing YouTube upload service."""
        metadata = request.metadata
        try:
            upload = self.youtube_service.upload_video(
                video_path=request.video_path,
                title=metadata.title,
                description=metadata.description,
                tags=metadata.tags,
                privacy_status=metadata.privacy_status,
                thumbnail_path=request.thumbnail_path,
                category_id=metadata.category or "22",
                publish_at=self._publish_at(metadata.publish_at),
            )
            return PublishResult(
                success=True,
                platform=self.platform_name,
                platform_video_id=upload.youtube_video_id,
                video_url=upload.youtube_url,
                processing_status=upload.processing_status,
                retryable=False,
                warnings=[],
                error=upload.error or None,
            )
        except Exception as exc:
            raise UploadError(str(exc)) from exc

    async def refresh_credentials(self) -> bool:
        """Refresh credentials by delegating to the OAuth status check."""
        connected, _channel, _scopes_valid, _error = await self.oauth_service.status()
        return connected

    async def supports_scheduling(self) -> bool:
        """YouTube supports scheduled publishing through publishAt."""
        return True

    def _publish_at(self, value: datetime | str | None) -> str | None:
        if isinstance(value, datetime):
            return value.isoformat()
        return value
