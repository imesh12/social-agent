from pydantic import BaseModel, Field


class TopicGenerateResponse(BaseModel):
    topic: str = Field(min_length=1)
    score: int = Field(ge=0, le=100)
