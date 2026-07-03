import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from services.utils.logging import get_rotating_logger

if TYPE_CHECKING:
    from services.llm.base_llm_service import BaseLLMService, LLMSEOResult

seo_intelligence_logger = get_rotating_logger("seo_intelligence", "seo_intelligence.log")


class SEOIntelligenceResult(BaseModel):
    """Quality analysis for a YouTube Shorts SEO package."""

    overall_score: int = Field(ge=0, le=100)
    title_score: int = Field(ge=0, le=100)
    description_score: int = Field(ge=0, le=100)
    keyword_score: int = Field(ge=0, le=100)
    tag_score: int = Field(ge=0, le=100)
    hashtag_score: int = Field(ge=0, le=100)
    search_intent_score: int = Field(ge=0, le=100)
    ctr_prediction: int = Field(ge=0, le=100)
    competition_level: str = Field(min_length=1)
    readability_score: int = Field(ge=0, le=100)
    engagement_score: int = Field(ge=0, le=100)
    recommended_title: str = Field(min_length=1)
    recommended_description: str = Field(min_length=1)
    recommended_tags: list[str] = Field(default_factory=list)
    recommended_hashtags: str = Field(min_length=1)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    recommended_changes: list[str] = Field(default_factory=list)
    accepted: bool = False
    attempt: int = Field(ge=0)
    analysis_timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    fallback_used: bool = False

    def score_summary(self) -> dict[str, object]:
        """Return metadata-ready SEO intelligence fields."""
        return self.model_dump()


class SEOIntelligenceSelection(BaseModel):
    """Best SEO package selected after intelligence scoring."""

    seo: Any
    intelligence: SEOIntelligenceResult
    attempt_count: int = Field(ge=1)


class SEOIntelligenceService:
    """Evaluate, improve, and select the best SEO metadata package."""

    acceptance_threshold = 85
    max_regeneration_attempts = 2

    def __init__(self, llm_service: "BaseLLMService") -> None:
        self.llm_service = llm_service

    def optimize_seo(self, script_text: str, initial_seo: "LLMSEOResult") -> SEOIntelligenceSelection:
        """Analyze SEO, improve if needed, and always return the best package."""
        best_seo = initial_seo
        best_result: SEOIntelligenceResult | None = None
        current = initial_seo
        attempts = self.max_regeneration_attempts + 1

        for attempt in range(attempts):
            result = self.analyze_seo(script_text=script_text, seo=current, attempt=attempt)
            if best_result is None or result.overall_score > best_result.overall_score:
                best_result = result
                best_seo = current

            if result.overall_score >= self.acceptance_threshold:
                break

            if attempt < attempts - 1:
                current = self._improve_seo(script_text=script_text, seo=current, analysis=result)

        if best_result is None:
            best_result = self._fallback_result(initial_seo, attempt=0)

        best_result.accepted = best_result.overall_score >= self.acceptance_threshold
        return SEOIntelligenceSelection(
            seo=best_seo,
            intelligence=best_result,
            attempt_count=best_result.attempt + 1,
        )

    def analyze_seo(self, script_text: str, seo: "LLMSEOResult", attempt: int) -> SEOIntelligenceResult:
        """Analyze one SEO package, failing soft with heuristic scores."""
        started_at = time.perf_counter()
        try:
            result = self.llm_service.analyze_seo_intelligence(script_text=script_text, seo=seo)
            result.attempt = attempt
            result.accepted = result.overall_score >= self.acceptance_threshold
            seo_intelligence_logger.info(
                "SEO intelligence attempt=%s score=%s title_score=%s ctr=%s accepted=%s elapsed=%.3fs fallback=%s",
                attempt,
                result.overall_score,
                result.title_score,
                result.ctr_prediction,
                result.accepted,
                time.perf_counter() - started_at,
                result.fallback_used,
            )
            return result
        except Exception:
            seo_intelligence_logger.exception("SEO intelligence failed attempt=%s", attempt)
            result = self._fallback_result(seo, attempt=attempt)
            seo_intelligence_logger.info(
                "SEO intelligence attempt=%s score=%s title_score=%s ctr=%s accepted=%s elapsed=%.3fs fallback=%s",
                attempt,
                result.overall_score,
                result.title_score,
                result.ctr_prediction,
                result.accepted,
                time.perf_counter() - started_at,
                True,
            )
            return result

    def _improve_seo(self, script_text: str, seo: "LLMSEOResult", analysis: SEOIntelligenceResult) -> "LLMSEOResult":
        try:
            return self.llm_service.improve_seo(script_text=script_text, seo=seo, analysis=analysis)
        except Exception:
            seo_intelligence_logger.exception("SEO improvement failed; using recommendations from analysis")
            return seo.__class__(
                title=analysis.recommended_title or seo.title,
                description=analysis.recommended_description or seo.description,
                tags=analysis.recommended_tags or seo.tags,
                hashtags=analysis.recommended_hashtags or seo.hashtags,
            )

    def _fallback_result(self, seo: "LLMSEOResult", attempt: int) -> SEOIntelligenceResult:
        title_length = len(seo.title)
        tag_count = len(seo.tags)
        title_score = 84 if 35 <= title_length <= 75 else 70
        tag_score = 84 if 3 <= tag_count <= 8 else 72
        hashtag_score = 82 if "#shorts" in seo.hashtags.lower() else 70
        overall = round((title_score * 0.25) + (tag_score * 0.2) + (hashtag_score * 0.15) + 76 * 0.4)
        return SEOIntelligenceResult(
            overall_score=overall,
            title_score=title_score,
            description_score=78,
            keyword_score=78,
            tag_score=tag_score,
            hashtag_score=hashtag_score,
            search_intent_score=76,
            ctr_prediction=max(0, overall - 4),
            competition_level="medium",
            readability_score=80,
            engagement_score=76,
            recommended_title=seo.title,
            recommended_description=seo.description,
            recommended_tags=seo.tags,
            recommended_hashtags=seo.hashtags,
            strengths=["Fallback analysis kept the SEO package usable."],
            weaknesses=["LLM SEO scoring was unavailable."],
            recommended_changes=[
                "make the title more specific",
                "align tags with search intent",
                "reduce duplicate wording",
            ],
            accepted=overall >= self.acceptance_threshold,
            attempt=attempt,
            fallback_used=True,
        )
