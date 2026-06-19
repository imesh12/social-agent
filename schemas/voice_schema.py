from pydantic import BaseModel, Field


class AudioGenerateRequest(BaseModel):
    script_id: int = Field(gt=0)
    voice: str = Field(default="en-US-JennyNeural", min_length=1)


class AudioGenerateResponse(BaseModel):
    audio_path: str = Field(min_length=1)
