import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx

from backend.config import get_settings
from services.llm.base_llm_service import BaseLLMService, LLMResearchResult, LLMSEOResult
from services.utils.retry import retry

logger = logging.getLogger(__name__)


class OllamaLLMService(BaseLLMService):
    def __init__(self) -> None:
        self.settings = get_settings()
        self.model = self.settings.ollama_model
        self.base_url = self.settings.ollama_base_url.rstrip("/")

    def research(self, topic: str) -> LLMResearchResult:
        try:
            prompt = self._load_prompt("research_prompt.txt").format(topic=topic)
            content = self._generate(prompt)
            payload = self._parse_json(content)
            return LLMResearchResult(facts=payload["facts"])
        except Exception:
            logger.exception("Ollama research failed after retries")
            raise RuntimeError("Ollama research failed") from None

    def generate_script(self, topic: str, facts: list[str]) -> str:
        try:
            prompt = self._load_prompt("script_prompt.txt").format(
                topic=topic,
                facts="\n".join(f"- {fact}" for fact in facts),
            )
            return self._strip_thinking(self._generate(prompt)).strip()
        except Exception:
            logger.exception("Ollama script generation failed after retries")
            raise RuntimeError("Ollama script generation failed") from None

    def review_script(self, script: str) -> str:
        try:
            prompt = self._load_prompt("script_review_prompt.txt").format(script=script)
            return self._strip_thinking(self._generate(prompt)).strip()
        except Exception:
            logger.exception("Ollama script review failed after retries")
            raise RuntimeError("Ollama script review failed") from None

    def generate_seo(self, script_text: str) -> LLMSEOResult:
        try:
            prompt = self._load_prompt("seo_prompt.txt").format(script_text=script_text)
            content = self._generate(prompt)
            payload = self._parse_json(content)
            return LLMSEOResult(
                title=payload["title"],
                description=payload["description"],
                tags=payload["tags"],
                hashtags=payload["hashtags"],
            )
        except Exception:
            logger.exception("Ollama SEO generation failed after retries")
            raise RuntimeError("Ollama SEO generation failed") from None

    @retry(max_attempts=3, initial_delay=1, backoff_multiplier=3, logger=logger)
    def _generate(self, prompt: str) -> str:
        logger.info("Calling Ollama model=%s", self.model)
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
        return str(data.get("response", "")).strip()

    def _load_prompt(self, name: str) -> str:
        return Path("prompts", name).read_text(encoding="utf-8")

    def _parse_json(self, content: str) -> dict[str, Any]:
        cleaned = self._strip_thinking(content)
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise ValueError("LLM response did not contain a JSON object")
        return json.loads(match.group(0))

    def _strip_thinking(self, content: str) -> str:
        return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE).strip()
