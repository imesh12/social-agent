from backend.config import get_settings
from services.llm.base_llm_service import BaseLLMService
from services.llm.ollama_llm_service import OllamaLLMService
from services.llm.openai_llm_service import OpenAILLMService


def build_llm_service() -> BaseLLMService:
    settings = get_settings()
    provider = settings.llm_provider.lower()
    if provider == "ollama":
        return OllamaLLMService()
    if provider == "openai":
        return OpenAILLMService()
    raise ValueError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")
