from pydantic import BaseModel, Field


class YouTubeChannelInfo(BaseModel):
    """Public channel details displayed in the dashboard."""

    channel_id: str = Field(default="")
    channel_name: str = Field(default="")
    channel_thumbnail: str = Field(default="")
    subscriber_count: int = Field(default=0, ge=0)
    video_count: int = Field(default=0, ge=0)
    country: str = Field(default="")
    default_language: str = Field(default="")


class YouTubeStatusResponse(BaseModel):
    connected: bool
    channel: YouTubeChannelInfo | None = None
    scopes_valid: bool = False
    error: str | None = None
