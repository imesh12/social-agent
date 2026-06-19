import logging

from pydantic import BaseModel, Field

from services.llm.base_llm_service import BaseLLMService

logger = logging.getLogger(__name__)


class ResearchResult(BaseModel):
    topic: str = Field(min_length=1)
    facts: list[str] = Field(min_length=1)


class ResearchAgent:
    def __init__(self, llm_service: BaseLLMService) -> None:
        self.llm_service = llm_service

    def research_topic(self, topic: str) -> ResearchResult:
        logger.info("Researching topic with LLM: %s", topic)
        result = self.llm_service.research(topic=topic)
        return ResearchResult(topic=topic, facts=result.facts)
