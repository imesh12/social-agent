from pydantic import BaseModel, Field


class ThumbnailGenerateRequest(BaseModel):
    video_id: int = Field(gt=0)


class ThumbnailGenerateResponse(BaseModel):
    thumbnail_path: str = Field(min_length=1)
