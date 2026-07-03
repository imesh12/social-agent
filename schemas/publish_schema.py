from pydantic import BaseModel, Field


class YouTubePublishRequest(BaseModel):
    video_id: int = Field(gt=0)


class YouTubePublishResponse(BaseModel):
    status: str = Field(min_length=1)
    youtube_url: str = ""
