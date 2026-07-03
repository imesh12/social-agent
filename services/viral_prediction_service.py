import json
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from services.utils.logging import get_rotating_logger

if TYPE_CHECKING:
    from services.llm.base_llm_service import BaseLLMService

viral_prediction_logger = get_rotating_logger("viral_prediction", "viral_prediction.log")


class ViralPredictionResult(BaseModel):
    """Predicted performance profile for a complete YouTube Shorts package."""

    viral_score: int = Field(ge=0, le=100)
    predicted_ctr: int = Field(ge=0, le=100)
    predicted_retention: int = Field(ge=0, le=100)
    shareability: str = Field(pattern="^(Low|Medium|High)$")
    uniqueness: str = Field(pattern="^(Low|Medium|High)$")
    competition: str = Field(pattern="^(Low|Medium|High)$")
    emotion: str = Field(min_length=1)
    risk_level: str = Field(pattern="^(Low|Medium|High)$")
    confidence: int = Field(ge=0, le=100)
    publish_recommendation: bool
    reasons: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    analysis_timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    fallback_used: bool = False

    def apply_publish_rules(self) -> "ViralPredictionResult":
        """Normalize publish recommendation according to viral score thresholds."""
        if self.viral_score >= 90:
            self.publish_recommendation = True
        elif self.viral_score >= 80:
            self.publish_recommendation = True
            if not self.improvements:
                self.improvements = ["tighten the hook", "increase thumbnail contrast", "strengthen the CTA"]
        else:
            self.publish_recommendation = False
            if not self.improvements:
                self.improvements = ["improve retention", "increase originality", "strengthen click appeal"]
        return self


class ViralPredictionService:
    """Predict viral potential from the complete local content package."""

    def __init__(self, llm_service: "BaseLLMService") -> None:
        self.llm_service = llm_service

    def predict(self, content_package: dict[str, Any]) -> ViralPredictionResult:
        """Return a viral prediction and never raise into the pipeline."""
        started_at = time.perf_counter()
        try:
            result = self.llm_service.analyze_viral_prediction(content_package=content_package)
            result.fallback_used = False
            result.apply_publish_rules()
            viral_prediction_logger.info(
                "Viral prediction score=%s ctr=%s retention=%s recommendation=%s confidence=%s elapsed=%.3fs fallback=%s",
                result.viral_score,
                result.predicted_ctr,
                result.predicted_retention,
                result.publish_recommendation,
                result.confidence,
                time.perf_counter() - started_at,
                False,
            )
            return result
        except Exception:
            viral_prediction_logger.exception("Viral prediction failed; using safe default")
            fallback = self._fallback_prediction(content_package)
            viral_prediction_logger.info(
                "Viral prediction score=%s ctr=%s retention=%s recommendation=%s confidence=%s elapsed=%.3fs fallback=%s",
                fallback.viral_score,
                fallback.predicted_ctr,
                fallback.predicted_retention,
                fallback.publish_recommendation,
                fallback.confidence,
                time.perf_counter() - started_at,
                True,
            )
            return fallback

    def _fallback_prediction(self, content_package: dict[str, Any]) -> ViralPredictionResult:
        script_score = self._nested_score(content_package.get("script_score"), "overall")
        content_score = self._nested_score(content_package.get("content_intelligence"), "overall_retention_score")
        thumbnail_score = self._nested_score(content_package.get("thumbnail_intelligence"), "overall_score")
        seo_score = self._nested_score(content_package.get("seo_intelligence"), "overall_score")
        scores = [score for score in (script_score, content_score, thumbnail_score, seo_score) if score is not None]
        viral_score = round(sum(scores) / len(scores)) if scores else 70
        return ViralPredictionResult(
            viral_score=viral_score,
            predicted_ctr=thumbnail_score or 68,
            predicted_retention=content_score or 68,
            shareability="Medium" if viral_score >= 75 else "Low",
            uniqueness="Medium",
            competition="Medium",
            emotion="estimated curiosity",
            risk_level="Medium" if viral_score < 80 else "Low",
            confidence=50,
            publish_recommendation=viral_score >= 80,
            reasons=["Fallback prediction used available local intelligence scores."],
            improvements=[
                "review hook-thumbnail alignment",
                "strengthen audience retention",
                "improve SEO specificity",
            ],
            fallback_used=True,
        ).apply_publish_rules()

    def _nested_score(self, value: Any, key: str) -> int | None:
        if isinstance(value, dict) and isinstance(value.get(key), int):
            return int(value[key])
        return None

    def package_to_prompt_json(self, content_package: dict[str, Any]) -> str:
        """Serialize a package for prompt use in tests and LLM services."""
        return json.dumps(content_package, indent=2, default=str)
