import logging
import time

from pydantic import BaseModel, Field

from agents.research_agent import ResearchResult
from services.content_intelligence_service import AudienceRetentionAnalysis, ContentIntelligenceService
from services.hook_intelligence_service import HookIntelligenceService, HookSelection
from services.llm.base_llm_service import BaseLLMService, ScriptScore
from services.utils.logging import get_rotating_logger
from services.version_selection_service import ScriptVersionEvaluation, VersionSelectionResult, VersionSelectionService

logger = logging.getLogger(__name__)
script_logger = get_rotating_logger("script_agent", "script.log")

ACCEPTANCE_THRESHOLD = 85
MAX_REGENERATION_ATTEMPTS = 2


class ScriptResult(BaseModel):
    content: str = Field(min_length=1)
    score: ScriptScore | None = None
    hook_selection: HookSelection | None = None
    content_intelligence: AudienceRetentionAnalysis | None = None
    version_selection: VersionSelectionResult | None = None
    accepted: bool = True
    regenerated: bool = False
    attempt_count: int = Field(default=1, ge=1)


class ScriptAgent:
    """Generate a script draft, review it, and return the final script."""

    def __init__(
        self,
        llm_service: BaseLLMService,
        hook_intelligence_service: HookIntelligenceService | None = None,
        content_intelligence_service: ContentIntelligenceService | None = None,
        version_selection_service: VersionSelectionService | None = None,
    ) -> None:
        self.llm_service = llm_service
        self.hook_intelligence_service = hook_intelligence_service or HookIntelligenceService()
        self.content_intelligence_service = content_intelligence_service or ContentIntelligenceService(llm_service)
        self.version_selection_service = version_selection_service or VersionSelectionService()

    def create_script(self, research: ResearchResult) -> ScriptResult:
        """Generate, review, score, and optionally regenerate a script."""
        started_at = time.perf_counter()
        verified_research = self._verified_research(research)
        hook_selection = self.hook_intelligence_service.generate_hooks(verified_research)
        try:
            return self._create_variant_script(
                research=verified_research,
                hook_selection=hook_selection,
                started_at=started_at,
            )
        except Exception:
            script_logger.exception(
                "Script variant generation failed topic=%s; falling back to single-script flow",
                research.topic,
            )
            return self._create_single_script(
                research=verified_research,
                hook_selection=hook_selection,
                started_at=started_at,
            )

    def _create_single_script(
        self,
        research: ResearchResult,
        hook_selection: HookSelection,
        started_at: float,
    ) -> ScriptResult:
        """Existing single-script generation and regeneration fallback."""
        best_content = ""
        best_score: ScriptScore | None = None
        attempt_count = 0
        max_attempts = MAX_REGENERATION_ATTEMPTS + 1

        for attempt in range(1, max_attempts + 1):
            attempt_count = attempt
            reviewed = self._generate_reviewed_script(
                research=research,
                hook_selection=hook_selection,
                attempt=attempt,
                started_at=started_at,
            )
            try:
                score = self.llm_service.score_script(script=reviewed)
            except Exception:
                script_logger.exception(
                    "Script scoring failure topic=%s attempt=%s elapsed=%.3fs; accepting reviewed script",
                    research.topic,
                    attempt,
                    time.perf_counter() - started_at,
                )
                return ScriptResult(
                    content=reviewed,
                    score=None,
                    hook_selection=hook_selection,
                    content_intelligence=self.content_intelligence_service.analyze_audience_retention(reviewed),
                    version_selection=None,
                    accepted=True,
                    regenerated=attempt > 1,
                    attempt_count=attempt,
                )

            if best_score is None or score.overall > best_score.overall:
                best_content = reviewed
                best_score = score

            if score.overall >= ACCEPTANCE_THRESHOLD:
                script_logger.info(
                    "Script score accepted topic=%s attempt=%s overall=%s regenerated=%s elapsed=%.3fs",
                    research.topic,
                    attempt,
                    score.overall,
                    attempt > 1,
                    time.perf_counter() - started_at,
                )
                script_logger.info(
                    "Final selected script score topic=%s overall=%s attempts=%s accepted=%s regenerated=%s",
                    research.topic,
                    score.overall,
                    attempt,
                    True,
                    attempt > 1,
                )
                return ScriptResult(
                    content=reviewed,
                    score=score,
                    hook_selection=hook_selection,
                    content_intelligence=self.content_intelligence_service.analyze_audience_retention(reviewed),
                    version_selection=None,
                    accepted=True,
                    regenerated=attempt > 1,
                    attempt_count=attempt,
                )

            should_regenerate = attempt < max_attempts
            script_logger.info(
                "Script score rejected topic=%s attempt=%s overall=%s regenerated=%s elapsed=%.3fs",
                research.topic,
                attempt,
                score.overall,
                should_regenerate,
                time.perf_counter() - started_at,
            )
            if should_regenerate:
                script_logger.info("Regenerating script topic=%s next_attempt=%s", research.topic, attempt + 1)

        selected_score = best_score
        script_logger.info(
            "Final selected script score topic=%s overall=%s attempts=%s accepted=%s regenerated=%s",
            research.topic,
            selected_score.overall if selected_score else None,
            attempt_count,
            selected_score.overall >= ACCEPTANCE_THRESHOLD if selected_score else True,
            attempt_count > 1,
        )
        return ScriptResult(
            content=best_content,
            score=selected_score,
            hook_selection=hook_selection,
            content_intelligence=self.content_intelligence_service.analyze_audience_retention(best_content),
            version_selection=None,
            accepted=selected_score.overall >= ACCEPTANCE_THRESHOLD if selected_score else True,
            regenerated=attempt_count > 1,
            attempt_count=attempt_count,
        )

    def _create_variant_script(
        self,
        research: ResearchResult,
        hook_selection: HookSelection,
        started_at: float,
    ) -> ScriptResult:
        """Generate three creative versions, evaluate each, and select the winner."""
        script_variants_logger = get_rotating_logger("script_variants", "script_variants.log")
        research_with_hooks = self._research_with_hooks(research, hook_selection)
        variants = self.llm_service.generate_script_variants(research=research_with_hooks)
        variant_map = {
            "A": variants.version_a,
            "B": variants.version_b,
            "C": variants.version_c,
        }
        evaluations: list[ScriptVersionEvaluation] = []
        for label, variant in variant_map.items():
            script_variants_logger.info(
                "Evaluating script variant label=%s focus=%s topic=%s",
                label,
                variant.focus,
                research.topic,
            )
            reviewed = self.llm_service.review_script(script=variant.script)
            script_score = self.llm_service.score_script(script=reviewed)
            content_intelligence = self.content_intelligence_service.analyze_audience_retention(reviewed)
            overall = self.version_selection_service.score_version(
                script_score=script_score,
                content_intelligence=content_intelligence,
                hook_score=hook_selection.selected_hook.overall_score,
            )
            evaluations.append(
                ScriptVersionEvaluation(
                    label=label,
                    focus=variant.focus,
                    draft_script=variant.script,
                    reviewed_script=reviewed,
                    script_score=script_score,
                    content_intelligence=content_intelligence,
                    hook_score=hook_selection.selected_hook.overall_score,
                    overall_score=overall,
                )
            )

        selection = self.version_selection_service.select(
            evaluations=evaluations,
            best_hook=hook_selection.selected_hook.text,
        )
        winner = next(item for item in evaluations if item.label == selection.winner)
        script_variants_logger.info(
            "Script variants complete winner=%s scores=%s elapsed=%.3fs",
            selection.winner,
            selection.scores,
            time.perf_counter() - started_at,
        )
        return ScriptResult(
            content=winner.reviewed_script,
            score=winner.script_score,
            hook_selection=hook_selection,
            content_intelligence=winner.content_intelligence,
            version_selection=selection,
            accepted=winner.script_score.overall >= ACCEPTANCE_THRESHOLD,
            regenerated=False,
            attempt_count=len(evaluations),
        )

    def _generate_reviewed_script(
        self,
        research: ResearchResult,
        hook_selection: HookSelection,
        attempt: int,
        started_at: float,
    ) -> str:
        """Generate a draft script and improve it through the LLM review step."""
        script_logger.info("Draft generation start topic=%s", research.topic)
        draft = self.llm_service.generate_script(research=self._research_with_hooks(research, hook_selection))
        script_logger.info(
            "Draft generation complete topic=%s attempt=%s elapsed=%.3fs",
            research.topic,
            attempt,
            time.perf_counter() - started_at,
        )

        review_started_at = time.perf_counter()
        script_logger.info("Review start topic=%s attempt=%s", research.topic, attempt)
        try:
            reviewed = self.llm_service.review_script(script=draft)
            script_logger.info(
                "Review success topic=%s attempt=%s elapsed=%.3fs total_elapsed=%.3fs",
                research.topic,
                attempt,
                time.perf_counter() - review_started_at,
                time.perf_counter() - started_at,
            )
            return reviewed
        except Exception:
            script_logger.exception(
                "Review failure topic=%s attempt=%s elapsed=%.3fs total_elapsed=%.3fs",
                research.topic,
                attempt,
                time.perf_counter() - review_started_at,
                time.perf_counter() - started_at,
            )
            return draft

    def _research_with_hooks(self, research: ResearchResult, hook_selection: HookSelection) -> ResearchResult:
        """Attach selected hook context to the package sent to the LLM."""
        data = research.model_dump()
        data["selected_hook"] = hook_selection.selected_hook.text
        data["top_hooks"] = [hook.text for hook in hook_selection.top_hooks]
        data["selection_reason"] = hook_selection.selection_reason
        return ResearchResult.model_validate(data)

    def _verified_research(self, research: ResearchResult) -> ResearchResult:
        """Prefer verified claims and remove rejected claims before script generation."""
        verification = research.fact_verification
        if verification is None:
            return research

        rejected = set(verification.rejected_claims)
        verified_claims = [claim for claim in verification.verified_claims if claim not in rejected]
        safe_facts = [
            fact
            for fact in research.interesting_facts
            if fact not in rejected
        ]
        safe_statistics = [
            statistic
            for statistic in research.statistics
            if statistic not in rejected
        ]

        prioritized = verified_claims + [fact for fact in safe_facts if fact not in verified_claims]
        if len(prioritized) < 3:
            prioritized.extend(
                claim
                for claim in verified_claims + safe_statistics
                if claim not in prioritized
            )
        prioritized = prioritized[:5]
        if len(prioritized) < 3:
            safe_padding = [
                research.summary,
                research.why_it_matters,
                research.video_angle,
            ]
            prioritized.extend(
                claim
                for claim in safe_padding
                if claim and claim not in rejected and claim not in prioritized
            )
        prioritized = prioritized[:5]

        return ResearchResult.model_validate(
            research.model_dump()
            | {
                "interesting_facts": prioritized,
                "statistics": safe_statistics,
            }
        )
