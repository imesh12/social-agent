from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class PublishMetadata:
    """Platform-neutral content metadata used by publisher adapters."""

    title: str
    description: str
    tags: list[str] = field(default_factory=list)
    category: str | None = None
    privacy_status: str = "private"
    publish_at: datetime | str | None = None


@dataclass(frozen=True)
class PublishRequest:
    """Platform-neutral publish request."""

    video_path: str
    metadata: PublishMetadata
    thumbnail_path: str | None = None


@dataclass(frozen=True)
class PublishResult:
    """Platform-neutral publish result returned by adapters."""

    success: bool
    platform: str
    platform_video_id: str | None = None
    video_url: str | None = None
    processing_status: str | None = None
    retryable: bool = False
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class ChannelInfo:
    """Connected publishing channel information."""

    platform: str
    channel_id: str
    channel_name: str
    channel_url: str | None = None
    thumbnail_url: str | None = None
    subscriber_count: int | None = None
    video_count: int | None = None
    country: str | None = None
    default_language: str | None = None


@dataclass(frozen=True)
class RetryDecision:
    """Retry guidance returned by adapters or platform error mappers."""

    retryable: bool
    delay_seconds: float | None = None
    reason: str | None = None


@dataclass(frozen=True)
class UploadSessionInfo:
    """Platform-neutral upload session metadata."""

    platform: str
    session_id: str | None = None
    upload_url: str | None = None
    expires_at: datetime | None = None
    bytes_uploaded: int | None = None
    total_bytes: int | None = None
