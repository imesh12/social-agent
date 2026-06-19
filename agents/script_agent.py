import logging
import time
from pathlib import Path

from pydantic import BaseModel, Field

from agents.research_agent import ResearchResult
from services.llm.base_llm_service import BaseLLMService

logger = logging.getLogger(__name__)
script_logger = logging.getLogger("script_agent")


def _configure_script_logger() -> None:
    """Attach a dedicated file handler for script-generation quality logs."""
    if any(isinstance(handler, logging.FileHandler) for handler in script_logger.handlers):
        return
    log_path = Path("storage/logs/script.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    script_logger.addHandler(handler)
    script_logger.setLevel(logging.INFO)
    script_logger.propagate = True


class ScriptResult(BaseModel):
    content: str = Field(min_length=1)


class ScriptAgent:
    """Generate a script draft, review it, and return the final script."""

    def __init__(self, llm_service: BaseLLMService) -> None:
        self.llm_service = llm_service
        _configure_script_logger()

    def create_script(self, research: ResearchResult) -> ScriptResult:
        """Generate a draft script and improve it through the LLM review step."""
        started_at = time.perf_counter()
        script_logger.info("Draft generation start topic=%s", research.topic)
        draft = self.llm_service.generate_script(topic=research.topic, facts=research.facts)
        script_logger.info(
            "Draft generation complete topic=%s elapsed=%.3fs",
            research.topic,
            time.perf_counter() - started_at,
        )

        review_started_at = time.perf_counter()
        script_logger.info("Review start topic=%s", research.topic)
        try:
            reviewed = self.llm_service.review_script(script=draft)
            script_logger.info(
                "Review success topic=%s elapsed=%.3fs total_elapsed=%.3fs",
                research.topic,
                time.perf_counter() - review_started_at,
                time.perf_counter() - started_at,
            )
            return ScriptResult(content=reviewed)
        except Exception:
            script_logger.exception(
                "Review failure topic=%s elapsed=%.3fs total_elapsed=%.3fs",
                research.topic,
                time.perf_counter() - review_started_at,
                time.perf_counter() - started_at,
            )
            return ScriptResult(content=draft)
