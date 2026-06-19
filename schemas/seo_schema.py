from pydantic import BaseModel, Field


class SEOGenerateRequest(BaseModel):
    video_id: int = Field(gt=0)


class SEOGenerateResponse(BaseModel):
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    tags: list[str] = Field(min_length=1)
    hashtags: str = Field(min_length=1)
