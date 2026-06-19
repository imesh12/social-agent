from pydantic import BaseModel, Field


class ScriptGenerateResponse(BaseModel):
    script: str = Field(min_length=1)
