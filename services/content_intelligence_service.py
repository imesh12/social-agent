import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from services.utils.logging import get_rotating_logger

if TYPE_CHECKING:
    from services.llm.base_llm_service import BaseLLMService

content_logger = get_rotating_logger("content_intelligence", "content_intelligence.log")


class AudienceRetentionAnalysis(BaseModel):
    """Audience-retention analysis for a short-form script."""

    overall_retention_score: int = Field(ge=0, le=100)
    opening_strength: int = Field(ge=0, le=100)
    first_5_seconds: int = Field(ge=0, le=100)
    curiosity_gap: int = Field(ge=0, le=100)
    story_flow: int = Field(ge=0, le=100)
    information_density: int = Field(ge=0, le=100)
    pace: int = Field(ge=0, le=100)
    emotional_trigger: int = Field(ge=0, le=100)
    ending_strength: int = Field(ge=0, le=100)
    drop_risk: str = Field(min_length=1)
    predicted_drop_points: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    analysis_timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    fallback_used: bool = False

    def score_summary(self) -> dict[str, int | str]:
        """Return compact fields for dashboard and metadata surfaces."""
        return {
            "overall_retention_score": self.overall_retention_score,
            "opening_strength": self.opening_strength,
            "first_5_seconds": self.first_5_seconds,
            "curiosity_gap": self.curiosity_gap,
            "story_flow": self.story_flow,
            "information_density": self.information_density,
            "pace": self.pace,
            "emotional_trigger": self.emotional_trigger,
            "ending_strength": self.ending_strength,
            "drop_risk": self.drop_risk,
        }


class ContentIntelligenceService:
    """Reusable content intelligence layer for script analysis."""

    def __init__(self, llm_service: "BaseLLMService") -> None:
        self.llm_service = llm_service

    def analyze_audience_retention(self, script: str) -> AudienceRetentionAnalysis:
        """Analyze a reviewed script for Shorts audience retention, failing soft."""
        started_at = time.perf_counter()
        try:
            analysis = self.llm_service.analyze_content_intelligence(script=script)
            analysis.fallback_used = False
            content_logger.info(
                "Audience retention analysis score=%s drop_risk=%s improvements=%s elapsed=%.3fs fallback=%s",
                analysis.overall_retention_score,
                analysis.drop_risk,
                analysis.improvements[:3],
                time.perf_counter() - started_at,
                False,
            )
            return analysis
        except Exception:
            content_logger.exception("Audience retention analysis failed; using fallback")
            fallback = self._fallback_analysis(script)
            content_logger.info(
                "Audience retention analysis score=%s drop_risk=%s improvements=%s elapsed=%.3fs fallback=%s",
                fallback.overall_retention_score,
                fallback.drop_risk,
                fallback.improvements[:3],
                time.perf_counter() - started_at,
                True,
            )
            return fallback

    def _fallback_analysis(self, script: str) -> AudienceRetentionAnalysis:
        sentences = [sentence.strip() for sentence in script.replace("\n", " ").split(".") if sentence.strip()]
        word_count = len(script.split())
        opening = sentences[0] if sentences else script[:80]
        pace = 82 if 80 <= word_count <= 120 else 68
        opening_strength = 82 if any(word in opening.lower() for word in ("why", "what", "most", "this", "stop")) else 70
        ending_strength = 80 if any(word in script.lower() for word in ("follow", "comment", "save", "try")) else 66
        overall = round((opening_strength * 0.25) + (pace * 0.25) + (ending_strength * 0.2) + 72 * 0.3)
        drop_point = "sentence 3" if len(sentences) >= 3 else "final sentence"
        return AudienceRetentionAnalysis(
            overall_retention_score=overall,
            opening_strength=opening_strength,
            first_5_seconds=opening_strength,
            curiosity_gap=72,
            story_flow=72,
            information_density=pace,
            pace=pace,
            emotional_trigger=70,
            ending_strength=ending_strength,
            drop_risk="medium" if overall < 80 else "low",
            predicted_drop_points=[drop_point],
            improvements=[
                "add curiosity",
                "improve transition",
                "stronger CTA",
            ],
            strengths=[
                "Script remains usable after fallback analysis.",
                "Opening and ending were checked with deterministic heuristics.",
            ],
            fallback_used=True,
        )
