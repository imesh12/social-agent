import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from services.utils.logging import get_rotating_logger

if TYPE_CHECKING:
    from services.llm.base_llm_service import BaseLLMService

publisher_decision_logger = get_rotating_logger("publisher_decision", "publisher_decision.log")


class PublisherDecisionResult(BaseModel):
    """Final publishing recommendation for a complete content package."""

    publish: bool
    confidence: int = Field(ge=0, le=100)
    overall_score: int = Field(ge=0, le=100)
    expected_views: int = Field(ge=0)
    expected_ctr: int = Field(ge=0, le=100)
    expected_retention: int = Field(ge=0, le=100)
    risk_level: str = Field(pattern="^(Low|Medium|High)$")
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    recommended_publish_time: str = Field(min_length=1)
    recommended_day: str = Field(min_length=1)
    reasoning: str = Field(min_length=1)
    analysis_timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    fallback_used: bool = False

    def apply_publish_rules(self) -> "PublisherDecisionResult":
        """Normalize publish recommendation from the final overall score."""
        if self.overall_score >= 90:
            self.publish = True
        elif self.overall_score >= 80:
            self.publish = True
            if not self.improvements:
                self.improvements = ["tighten the title", "increase thumbnail contrast", "sharpen the first line"]
        else:
            self.publish = False
            if not self.improvements:
                self.improvements = ["improve retention", "strengthen click appeal", "reduce factual risk"]
        return self


class PublisherDecisionService:
    """Evaluate whether a complete YouTube Shorts package is ready to publish."""

    def __init__(self, llm_service: "BaseLLMService") -> None:
        self.llm_service = llm_service

    def decide(self, content_package: dict[str, Any]) -> PublisherDecisionResult:
        """Return a final publishing decision, falling back without raising."""
        started_at = time.perf_counter()
        try:
            result = self.llm_service.analyze_publisher_decision(content_package=content_package)
            result.fallback_used = False
            result.apply_publish_rules()
            self._log_result(result, time.perf_counter() - started_at)
            return result
        except Exception:
            publisher_decision_logger.exception("Publisher decision failed; using safe fallback")
            fallback = self._fallback_decision(content_package)
            self._log_result(fallback, time.perf_counter() - started_at)
            return fallback

    def _fallback_decision(self, content_package: dict[str, Any]) -> PublisherDecisionResult:
        viral = content_package.get("viral_prediction")
        script_score = self._nested_score(content_package.get("script_score"), "overall")
        retention = self._nested_score(content_package.get("content_intelligence"), "overall_retention_score")
        thumbnail = self._nested_score(content_package.get("thumbnail_intelligence"), "overall_score")
        seo = self._nested_score(content_package.get("seo_intelligence"), "overall_score")
        viral_score = self._nested_score(viral, "viral_score")
        scores = [score for score in (script_score, retention, thumbnail, seo, viral_score) if score is not None]
        overall = round(sum(scores) / len(scores)) if scores else 70
        expected_ctr = self._nested_score(viral, "predicted_ctr") or self._nested_score(
            content_package.get("thumbnail_intelligence"), "ctr_prediction"
        ) or 65
        expected_retention = self._nested_score(viral, "predicted_retention") or retention or 65
        return PublisherDecisionResult(
            publish=overall >= 80,
            confidence=50,
            overall_score=overall,
            expected_views=1000 if overall >= 80 else 300,
            expected_ctr=expected_ctr,
            expected_retention=expected_retention,
            risk_level="Low" if overall >= 90 else "Medium" if overall >= 80 else "High",
            strengths=["Fallback decision used available local intelligence scores."],
            weaknesses=["AI publisher decision was unavailable."],
            improvements=["review final package manually", "check thumbnail and title alignment", "verify factual claims"],
            recommended_publish_time="18:00",
            recommended_day="Today",
            reasoning="Estimated from script, retention, thumbnail, SEO, and viral prediction scores.",
            fallback_used=True,
        ).apply_publish_rules()

    def _nested_score(self, value: Any, key: str) -> int | None:
        if isinstance(value, dict) and isinstance(value.get(key), int):
            return int(value[key])
        return None

    def _log_result(self, result: PublisherDecisionResult, elapsed: float) -> None:
        publisher_decision_logger.info(
            "Publisher decision score=%s publish=%s confidence=%s risk=%s expected_ctr=%s expected_retention=%s elapsed=%.3fs fallback=%s",
            result.overall_score,
            result.publish,
            result.confidence,
            result.risk_level,
            result.expected_ctr,
            result.expected_retention,
            elapsed,
            result.fallback_used,
        )
