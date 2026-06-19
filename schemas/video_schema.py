from pydantic import BaseModel, Field


class VideoGenerateRequest(BaseModel):
    audio_id: int = Field(gt=0)


class VideoGenerateResponse(BaseModel):
    video_path: str = Field(min_length=1)
