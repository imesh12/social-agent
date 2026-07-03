from pathlib import Path

from services.content_intelligence_service import AudienceRetentionAnalysis
from services.llm.base_llm_service import ScriptScore
from services.version_selection_service import ScriptVersionEvaluation, VersionSelectionService


def script_score(score: int) -> ScriptScore:
    return ScriptScore(
        hook=score,
        clarity=score,
        retention=score,
        storytelling=score,
        cta=score,
        overall=score,
        strengths=["clear"],
        improvements=[],
    )


def retention(score: int) -> AudienceRetentionAnalysis:
    return AudienceRetentionAnalysis(
        overall_retention_score=score,
        opening_strength=score,
        first_5_seconds=score,
        curiosity_gap=score,
        story_flow=score,
        information_density=score,
        pace=score,
        emotional_trigger=score,
        ending_strength=score,
        drop_risk="low",
        predicted_drop_points=[],
        improvements=[],
        strengths=["good pace"],
        fallback_used=False,
    )


def evaluation(label: str, score: int) -> ScriptVersionEvaluation:
    content = retention(score)
    service = VersionSelectionService()
    return ScriptVersionEvaluation(
        label=label,
        focus=f"Version {label}",
        draft_script=f"draft {label}",
        reviewed_script=f"reviewed {label}",
        script_score=script_score(score),
        content_intelligence=content,
        hook_score=score,
        overall_score=service.score_version(script_score(score), content, score),
    )


def test_version_selection_picks_highest_score() -> None:
    service = VersionSelectionService()
    result = service.select(
        evaluations=[evaluation("A", 80), evaluation("B", 95), evaluation("C", 89)],
        best_hook="Best hook",
    )

    assert result.winner == "B"
    assert result.scores == {"A": 80, "B": 95, "C": 89}
    assert result.best_hook == "Best hook"


def test_version_selection_logging() -> None:
    service = VersionSelectionService()

    service.select([evaluation("A", 90)], best_hook="Best hook")

    assert Path("storage/logs/script_variants.log").exists()
