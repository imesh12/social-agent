import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from services.utils.logging import get_rotating_logger

if TYPE_CHECKING:
    from services.llm.base_llm_service import BaseLLMService

thumbnail_intelligence_logger = get_rotating_logger("thumbnail_intelligence", "thumbnail_intelligence.log")


class ThumbnailIntelligenceResult(BaseModel):
    """CTR-focused thumbnail intelligence result."""

    overall_score: int = Field(ge=0, le=100)
    ctr_prediction: int = Field(ge=0, le=100)
    curiosity_score: int = Field(ge=0, le=100)
    emotion_score: int = Field(ge=0, le=100)
    contrast_score: int = Field(ge=0, le=100)
    visual_clarity: int = Field(ge=0, le=100)
    mobile_visibility: int = Field(ge=0, le=100)
    text_readability: int = Field(ge=0, le=100)
    subject_focus: int = Field(ge=0, le=100)
    brand_consistency: int = Field(ge=0, le=100)
    recommended_changes: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    regeneration_attempt: int = Field(ge=0)
    accepted: bool = False
    selected_thumbnail_path: str = Field(default="")
    analysis_timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    fallback_used: bool = False

    def score_summary(self) -> dict[str, int | str | bool | list[str]]:
        """Return metadata-ready thumbnail intelligence fields."""
        return {
            "overall_score": self.overall_score,
            "ctr_prediction": self.ctr_prediction,
            "curiosity_score": self.curiosity_score,
            "emotion_score": self.emotion_score,
            "contrast_score": self.contrast_score,
            "visual_clarity": self.visual_clarity,
            "mobile_visibility": self.mobile_visibility,
            "text_readability": self.text_readability,
            "subject_focus": self.subject_focus,
            "brand_consistency": self.brand_consistency,
            "recommended_changes": self.recommended_changes,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "regeneration_attempt": self.regeneration_attempt,
            "accepted": self.accepted,
            "selected_thumbnail_path": self.selected_thumbnail_path,
            "analysis_timestamp": self.analysis_timestamp,
            "fallback_used": self.fallback_used,
        }


class ThumbnailIntelligenceService:
    """Evaluate thumbnail CTR potential and keep the best generated attempt."""

    acceptance_threshold = 85
    max_regeneration_attempts = 2

    def __init__(self, llm_service: "BaseLLMService") -> None:
        self.llm_service = llm_service

    def analyze_thumbnail(self, thumbnail_path: str, attempt: int = 0) -> ThumbnailIntelligenceResult:
        """Analyze one thumbnail attempt, failing soft with heuristic scores."""
        started_at = time.perf_counter()
        try:
            result = self.llm_service.analyze_thumbnail_intelligence(thumbnail_path=thumbnail_path)
            result.regeneration_attempt = attempt
            result.selected_thumbnail_path = thumbnail_path
            result.accepted = result.overall_score >= self.acceptance_threshold
            thumbnail_intelligence_logger.info(
                "Thumbnail intelligence path=%s attempt=%s score=%s ctr=%s accepted=%s elapsed=%.3fs fallback=%s",
                thumbnail_path,
                attempt,
                result.overall_score,
                result.ctr_prediction,
                result.accepted,
                time.perf_counter() - started_at,
                result.fallback_used,
            )
            return result
        except Exception:
            thumbnail_intelligence_logger.exception("Thumbnail intelligence failed path=%s attempt=%s", thumbnail_path, attempt)
            result = self._fallback_result(thumbnail_path=thumbnail_path, attempt=attempt)
            thumbnail_intelligence_logger.info(
                "Thumbnail intelligence path=%s attempt=%s score=%s ctr=%s accepted=%s elapsed=%.3fs fallback=%s",
                thumbnail_path,
                attempt,
                result.overall_score,
                result.ctr_prediction,
                result.accepted,
                time.perf_counter() - started_at,
                True,
            )
            return result

    def select_best_thumbnail(
        self,
        output_path: str,
        attempt_paths: list[str],
    ) -> ThumbnailIntelligenceResult:
        """Analyze attempts, regenerate up to the limit, and copy the best to output_path."""
        best_result: ThumbnailIntelligenceResult | None = None
        for attempt, path in enumerate(attempt_paths):
            result = self.analyze_thumbnail(thumbnail_path=path, attempt=attempt)
            if best_result is None or result.overall_score > best_result.overall_score:
                best_result = result
            if result.overall_score >= self.acceptance_threshold:
                break

        if best_result is None:
            best_result = self._fallback_result(output_path, attempt=0)

        selected_path = best_result.selected_thumbnail_path or output_path
        if selected_path != output_path and Path(selected_path).exists():
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(selected_path, output_path)

        best_result.selected_thumbnail_path = output_path
        best_result.accepted = best_result.overall_score >= self.acceptance_threshold
        return best_result

    def _fallback_result(self, thumbnail_path: str, attempt: int) -> ThumbnailIntelligenceResult:
        path = Path(thumbnail_path)
        exists_bonus = 8 if path.exists() else 0
        score = 72 + exists_bonus
        return ThumbnailIntelligenceResult(
            overall_score=score,
            ctr_prediction=max(0, score - 5),
            curiosity_score=70,
            emotion_score=66,
            contrast_score=78,
            visual_clarity=76,
            mobile_visibility=74,
            text_readability=76,
            subject_focus=68,
            brand_consistency=72,
            recommended_changes=[
                "use four words or fewer",
                "increase subject focus",
                "add stronger emotional contrast",
            ],
            strengths=["Thumbnail file exists and can continue through the pipeline."],
            weaknesses=["Fallback analysis cannot inspect visual semantics."],
            regeneration_attempt=attempt,
            accepted=score >= self.acceptance_threshold,
            selected_thumbnail_path=thumbnail_path,
            fallback_used=True,
        )
