from pydantic import BaseModel, Field

from services.content_intelligence_service import AudienceRetentionAnalysis
from services.llm.base_llm_service import ScriptScore
from services.utils.logging import get_rotating_logger

script_variants_logger = get_rotating_logger("script_variants", "script_variants.log")


class ScriptVersionEvaluation(BaseModel):
    """Evaluation data for one creative script version."""

    label: str = Field(pattern="^[ABC]$")
    focus: str = Field(min_length=1)
    draft_script: str = Field(min_length=1)
    reviewed_script: str = Field(min_length=1)
    script_score: ScriptScore
    content_intelligence: AudienceRetentionAnalysis
    hook_score: int = Field(ge=0, le=100)
    overall_score: int = Field(ge=0, le=100)


class VersionSelectionResult(BaseModel):
    """Winner and score summary for creative script versions."""

    winner: str = Field(pattern="^[ABC]$")
    scores: dict[str, int]
    reason: str = Field(min_length=1)
    evaluations: list[ScriptVersionEvaluation] = Field(default_factory=list)
    best_hook: str = Field(default="")


class VersionSelectionService:
    """Select the strongest creative script version from evaluated variants."""

    def score_version(
        self,
        script_score: ScriptScore,
        content_intelligence: AudienceRetentionAnalysis,
        hook_score: int,
    ) -> int:
        """Compute weighted score from quality, retention, hook strength, and pace."""
        retention_prediction = round(
            (
                content_intelligence.first_5_seconds
                + content_intelligence.curiosity_gap
                + content_intelligence.pace
            )
            / 3
        )
        return round(
            script_score.overall * 0.35
            + content_intelligence.overall_retention_score * 0.30
            + hook_score * 0.15
            + retention_prediction * 0.20
        )

    def select(
        self,
        evaluations: list[ScriptVersionEvaluation],
        best_hook: str,
    ) -> VersionSelectionResult:
        """Return the highest scoring evaluated version."""
        if not evaluations:
            raise ValueError("At least one script version evaluation is required")

        ordered = sorted(evaluations, key=lambda item: item.overall_score, reverse=True)
        winner = ordered[0]
        scores = {item.label: item.overall_score for item in evaluations}
        reason = (
            f"Version {winner.label} had the strongest combined script quality, "
            "predicted retention, and hook strength."
        )
        script_variants_logger.info(
            "Version selection winner=%s scores=%s reason=%s",
            winner.label,
            scores,
            reason,
        )
        return VersionSelectionResult(
            winner=winner.label,
            scores=scores,
            reason=reason,
            evaluations=evaluations,
            best_hook=best_hook,
        )
