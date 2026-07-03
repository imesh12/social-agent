from pydantic import BaseModel, Field


class AuthUser(BaseModel):
    """Minimal authenticated Google profile stored in the browser session."""

    email: str = Field(default="")
    name: str = Field(default="")
    picture: str = Field(default="")


class AuthStatusResponse(BaseModel):
    authenticated: bool
    user: AuthUser | None = None
