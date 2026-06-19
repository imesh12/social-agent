from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class LLMResearchResult(BaseModel):
    facts: list[str] = Field(min_length=1)


class LLMSEOResult(BaseModel):
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    tags: list[str] = Field(min_length=1)
    hashtags: str = Field(min_length=1)


class BaseLLMService(ABC):
    @abstractmethod
    def research(self, topic: str) -> LLMResearchResult:
        raise NotImplementedError

    @abstractmethod
    def generate_script(self, topic: str, facts: list[str]) -> str:
        raise NotImplementedError

    @abstractmethod
    def review_script(self, script: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_seo(self, script_text: str) -> LLMSEOResult:
        raise NotImplementedError
