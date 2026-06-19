from pydantic import BaseModel, Field


class SubtitleGenerateRequest(BaseModel):
    video_id: int = Field(gt=0)


class SubtitleGenerateResponse(BaseModel):
    subtitle_path: str = Field(min_length=1)
