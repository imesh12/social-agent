from services.llm.base_llm_service import BaseLLMService, LLMResearchResult, LLMSEOResult


class OpenAILLMService(BaseLLMService):
    def research(self, topic: str) -> LLMResearchResult:
        raise NotImplementedError("OpenAI LLM provider is not implemented yet")

    def generate_script(self, topic: str, facts: list[str]) -> str:
        raise NotImplementedError("OpenAI LLM provider is not implemented yet")

    def review_script(self, script: str) -> str:
        raise NotImplementedError("OpenAI LLM provider is not implemented yet")

    def generate_seo(self, script_text: str) -> LLMSEOResult:
        raise NotImplementedError("OpenAI LLM provider is not implemented yet")
