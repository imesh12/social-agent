import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import httpx

from backend.config import get_settings
from services.competitor_analysis_service import CompetitorAnalysis
from services.content_intelligence_service import AudienceRetentionAnalysis
from services.llm.base_llm_service import BaseLLMService, LLMResearchResult, LLMSEOResult, ScriptScore, ScriptVariants
from services.publisher_decision_service import PublisherDecisionResult
from services.seo_intelligence_service import SEOIntelligenceResult
from services.thumbnail_intelligence_service import ThumbnailIntelligenceResult
from services.viral_prediction_service import ViralPredictionResult
from services.llm.profiling import (
    estimate_tokens,
    gpu_snapshot,
    log_profile_event,
    next_retry_attempt,
    process_memory_bytes,
    profile_operation,
    system_cpu_percent,
)
from services.utils.retry import retry

logger = logging.getLogger(__name__)


class OllamaLLMService(BaseLLMService):
    def __init__(self) -> None:
        self.settings = get_settings()
        self.model = self.settings.ollama_model
        self.base_url = self.settings.ollama_base_url.rstrip("/")

    def research(self, topic: str, competitor_analysis: CompetitorAnalysis | None = None) -> LLMResearchResult:
        try:
            prompt = self._load_prompt("research_prompt.txt").format(
                topic=topic,
                competitor_analysis=competitor_analysis.model_dump_json(indent=2) if competitor_analysis else "{}",
            )
            with profile_operation("research", "research_prompt.txt", prompt):
                content = self._generate(prompt)
                payload = self._parse_json(content)
                result = LLMResearchResult.model_validate(payload)
                if result.competitor_analysis is None:
                    result.competitor_analysis = competitor_analysis
                return result
        except Exception:
            logger.exception("Ollama research failed after retries")
            raise RuntimeError("Ollama research failed") from None

    def generate_script(self, research: LLMResearchResult) -> str:
        try:
            prompt = self._load_prompt("script_prompt.txt").format(
                research_package=research.model_dump_json(indent=2),
            )
            with profile_operation("generate_script", "script_prompt.txt", prompt):
                return self._strip_thinking(self._generate(prompt)).strip()
        except Exception:
            logger.exception("Ollama script generation failed after retries")
            raise RuntimeError("Ollama script generation failed") from None

    def generate_script_variants(self, research: LLMResearchResult) -> ScriptVariants:
        try:
            prompt = self._load_prompt("script_variants_prompt.txt").format(
                research_package=research.model_dump_json(indent=2),
            )
            with profile_operation("generate_script_variants", "script_variants_prompt.txt", prompt):
                content = self._generate(prompt)
                payload = self._parse_json(content)
                return ScriptVariants.model_validate(payload)
        except Exception:
            logger.exception("Ollama script variant generation failed after retries")
            raise RuntimeError("Ollama script variant generation failed") from None

    def review_script(self, script: str) -> str:
        try:
            prompt = self._load_prompt("script_review_prompt.txt").format(script=script)
            with profile_operation("review_script", "script_review_prompt.txt", prompt):
                return self._strip_thinking(self._generate(prompt)).strip()
        except Exception:
            logger.exception("Ollama script review failed after retries")
            raise RuntimeError("Ollama script review failed") from None

    def score_script(self, script: str) -> ScriptScore:
        try:
            prompt = self._load_prompt("script_score_prompt.txt").format(script=script)
            with profile_operation("score_script", "script_score_prompt.txt", prompt):
                content = self._generate(prompt)
                payload = self._parse_json(content)
                return ScriptScore.model_validate(payload)
        except Exception:
            logger.exception("Ollama script scoring failed after retries")
            raise RuntimeError("Ollama script scoring failed") from None

    def analyze_content_intelligence(self, script: str) -> AudienceRetentionAnalysis:
        try:
            prompt = self._load_prompt("content_intelligence_prompt.txt").format(script=script)
            with profile_operation("analyze_content_intelligence", "content_intelligence_prompt.txt", prompt):
                content = self._generate(prompt)
                payload = self._parse_json(content)
                return AudienceRetentionAnalysis.model_validate(payload)
        except Exception:
            logger.exception("Ollama content intelligence analysis failed after retries")
            raise RuntimeError("Ollama content intelligence analysis failed") from None

    def analyze_thumbnail_intelligence(self, thumbnail_path: str) -> ThumbnailIntelligenceResult:
        try:
            prompt = self._load_prompt("thumbnail_intelligence_prompt.txt").format(thumbnail_path=thumbnail_path)
            with profile_operation("analyze_thumbnail_intelligence", "thumbnail_intelligence_prompt.txt", prompt):
                content = self._generate(prompt)
                payload = self._parse_json(content)
                return ThumbnailIntelligenceResult.model_validate(payload)
        except Exception:
            logger.exception("Ollama thumbnail intelligence analysis failed after retries")
            raise RuntimeError("Ollama thumbnail intelligence analysis failed") from None

    def analyze_seo_intelligence(self, script_text: str, seo: LLMSEOResult) -> SEOIntelligenceResult:
        try:
            prompt = self._load_prompt("seo_intelligence_prompt.txt").format(
                script_text=script_text,
                seo_package=seo.model_dump_json(indent=2),
            )
            with profile_operation("analyze_seo_intelligence", "seo_intelligence_prompt.txt", prompt):
                content = self._generate(prompt)
                payload = self._parse_json(content)
                return SEOIntelligenceResult.model_validate(payload)
        except Exception:
            logger.exception("Ollama SEO intelligence analysis failed after retries")
            raise RuntimeError("Ollama SEO intelligence analysis failed") from None

    def improve_seo(self, script_text: str, seo: LLMSEOResult, analysis: SEOIntelligenceResult) -> LLMSEOResult:
        try:
            prompt = self._load_prompt("seo_improvement_prompt.txt").format(
                script_text=script_text,
                seo_package=seo.model_dump_json(indent=2),
                seo_analysis=analysis.model_dump_json(indent=2),
            )
            with profile_operation("improve_seo", "seo_improvement_prompt.txt", prompt):
                content = self._generate(prompt)
                payload = self._parse_json(content)
                return LLMSEOResult(
                    title=payload["title"],
                    description=payload["description"],
                    tags=payload["tags"],
                    hashtags=payload["hashtags"],
                )
        except Exception:
            logger.exception("Ollama SEO improvement failed after retries")
            raise RuntimeError("Ollama SEO improvement failed") from None

    def analyze_viral_prediction(self, content_package: dict) -> ViralPredictionResult:
        try:
            prompt = self._load_prompt("viral_prediction_prompt.txt").format(
                content_package=json.dumps(content_package, indent=2, default=str),
            )
            with profile_operation("analyze_viral_prediction", "viral_prediction_prompt.txt", prompt):
                content = self._generate(prompt)
                payload = self._parse_json(content)
                return ViralPredictionResult.model_validate(payload).apply_publish_rules()
        except Exception:
            logger.exception("Ollama viral prediction analysis failed after retries")
            raise RuntimeError("Ollama viral prediction analysis failed") from None

    def analyze_publisher_decision(self, content_package: dict) -> PublisherDecisionResult:
        try:
            prompt = self._load_prompt("publisher_decision_prompt.txt").format(
                content_package=json.dumps(content_package, indent=2, default=str),
            )
            with profile_operation("analyze_publisher_decision", "publisher_decision_prompt.txt", prompt):
                content = self._generate(prompt)
                payload = self._parse_json(content)
                return PublisherDecisionResult.model_validate(payload).apply_publish_rules()
        except Exception:
            logger.exception("Ollama publisher decision analysis failed after retries")
            raise RuntimeError("Ollama publisher decision analysis failed") from None

    def generate_seo(self, script_text: str) -> LLMSEOResult:
        try:
            prompt = self._load_prompt("seo_prompt.txt").format(script_text=script_text)
            with profile_operation("generate_seo", "seo_prompt.txt", prompt):
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
        attempt = next_retry_attempt()
        timeout_seconds = 120.0
        memory_before = process_memory_bytes()
        cpu_before = time.process_time()
        system_cpu_before = system_cpu_percent()
        gpu_before = gpu_snapshot()
        request_started_at = time.perf_counter()
        logger.info("Calling Ollama model=%s", self.model)
        log_profile_event(
            "llm_http_request_started",
            model=self.model,
            base_url=self.base_url,
            rendered_prompt_size_bytes=len(prompt.encode("utf-8")),
            timeout_seconds=timeout_seconds,
            memory_before_bytes=memory_before,
            system_cpu_before_percent=system_cpu_before,
            gpu_before=gpu_before,
            retry_attempt=attempt,
        )
        try:
            with httpx.Client(timeout=timeout_seconds) as client:
                with client.stream(
                    "POST",
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                    },
                ) as response:
                    response_headers_at = time.perf_counter()
                    chunks: list[bytes] = []
                    first_byte_at: float | None = None
                    for chunk in response.iter_bytes():
                        if chunk and first_byte_at is None:
                            first_byte_at = time.perf_counter()
                        chunks.append(chunk)
                    response_completed_at = time.perf_counter()
                    body = b"".join(chunks)
                    response.raise_for_status()
                    text = body.decode(response.encoding or "utf-8", errors="replace")
                    data = json.loads(text)
        except Exception as exc:
            completed_at = time.perf_counter()
            memory_after = process_memory_bytes()
            cpu_after = time.process_time()
            log_profile_event(
                "llm_http_request_failed",
                model=self.model,
                timeout_seconds=timeout_seconds,
                http_response_first_byte_seconds=None,
                http_response_completed_seconds=completed_at - request_started_at,
                generation_duration_seconds=completed_at - request_started_at,
                total_request_duration_seconds=completed_at - request_started_at,
                memory_before_bytes=memory_before,
                memory_after_bytes=memory_after,
                memory_delta_bytes=(memory_after - memory_before) if memory_before is not None and memory_after is not None else None,
                process_cpu_seconds=cpu_after - cpu_before,
                process_cpu_percent=((cpu_after - cpu_before) / max(completed_at - request_started_at, 0.001)) * 100,
                system_cpu_before_percent=system_cpu_before,
                system_cpu_after_percent=system_cpu_percent(),
                gpu_before=gpu_before,
                gpu_after=gpu_snapshot(),
                exception_type=type(exc).__name__,
                exception_message=str(exc),
                retry_attempt=attempt,
            )
            raise

        completed_at = time.perf_counter()
        completion = str(data.get("response", "")).strip()
        completion_tokens = estimate_tokens(completion)
        generation_duration = response_completed_at - request_started_at
        memory_after = process_memory_bytes()
        cpu_after = time.process_time()
        log_profile_event(
            "llm_http_request_completed",
            model=self.model,
            timeout_seconds=timeout_seconds,
            http_status_code=response.status_code,
            http_request_start_seconds=0.0,
            http_response_headers_seconds=response_headers_at - request_started_at,
            http_response_first_byte_seconds=(first_byte_at - request_started_at) if first_byte_at is not None else None,
            http_response_completed_seconds=response_completed_at - request_started_at,
            generation_duration_seconds=generation_duration,
            completion_characters=len(completion),
            estimated_completion_tokens=completion_tokens,
            tokens_per_second=completion_tokens / generation_duration if generation_duration > 0 else None,
            total_request_duration_seconds=completed_at - request_started_at,
            memory_before_bytes=memory_before,
            memory_after_bytes=memory_after,
            memory_delta_bytes=(memory_after - memory_before) if memory_before is not None and memory_after is not None else None,
            process_cpu_seconds=cpu_after - cpu_before,
            process_cpu_percent=((cpu_after - cpu_before) / max(completed_at - request_started_at, 0.001)) * 100,
            system_cpu_before_percent=system_cpu_before,
            system_cpu_after_percent=system_cpu_percent(),
            gpu_before=gpu_before,
            gpu_after=gpu_snapshot(),
            retry_attempt=attempt,
        )
        return completion

    def _load_prompt(self, name: str) -> str:
        return Path("prompts", name).read_text(encoding="utf-8")

    def _parse_json(self, content: str) -> dict[str, Any]:
        started_at = time.perf_counter()
        try:
            cleaned = self._strip_thinking(content)
            match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
            if not match:
                raise ValueError("LLM response did not contain a JSON object")
            parsed = json.loads(match.group(0))
            log_profile_event(
                "llm_json_parse_completed",
                json_parsing_duration_seconds=time.perf_counter() - started_at,
                completion_characters=len(content),
                estimated_completion_tokens=estimate_tokens(content),
                status="success",
            )
            return parsed
        except Exception as exc:
            log_profile_event(
                "llm_json_parse_failed",
                json_parsing_duration_seconds=time.perf_counter() - started_at,
                completion_characters=len(content),
                estimated_completion_tokens=estimate_tokens(content),
                status="error",
                exception_type=type(exc).__name__,
                exception_message=str(exc),
            )
            raise

    def _strip_thinking(self, content: str) -> str:
        return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE).strip()
