import logging

from services.competitor_analysis_service import CompetitorAnalysis, CompetitorAnalysisService
from services.fact_verification_service import FactVerificationService
from services.llm.base_llm_service import BaseLLMService, LLMResearchResult
from services.utils.logging import get_rotating_logger

logger = logging.getLogger(__name__)
research_logger = get_rotating_logger("research_agent", "research.log")


class ResearchResult(LLMResearchResult):
    """Structured research package consumed by downstream content agents."""


class ResearchAgent:
    """Generate structured, creator-focused research for a topic."""

    def __init__(
        self,
        llm_service: BaseLLMService,
        competitor_analysis_service: CompetitorAnalysisService | None = None,
        fact_verification_service: FactVerificationService | None = None,
    ) -> None:
        self.llm_service = llm_service
        self.competitor_analysis_service = competitor_analysis_service or CompetitorAnalysisService(
            llm_service=llm_service
        )
        self.fact_verification_service = fact_verification_service or FactVerificationService()

    def research_topic(self, topic: str) -> ResearchResult:
        """Return structured research, falling back to a safe package on LLM failure."""
        logger.info("Researching topic with LLM: %s", topic)
        competitor_analysis = self.competitor_analysis_service.analyze(topic)
        research_logger.info(
            "Competitor analysis complete topic=%s originality_score=%s chosen_angle=%s fallback_usage=%s",
            topic,
            competitor_analysis.originality_score,
            competitor_analysis.unique_video_angle,
            len(competitor_analysis.competitor_titles) == 0,
        )
        try:
            result = self.llm_service.research(topic=topic, competitor_analysis=competitor_analysis)
            research = ResearchResult.model_validate(result.model_dump())
            if research.competitor_analysis is None:
                research.competitor_analysis = competitor_analysis
            research.fact_verification = self.fact_verification_service.verify(research)
            research_logger.info(
                "Fact verification complete topic=%s claims_checked=%s verified=%s rejected=%s overall_confidence=%s fallback_usage=%s",
                topic,
                len(research.fact_verification.claim_details),
                len(research.fact_verification.verified_claims),
                len(research.fact_verification.rejected_claims),
                research.fact_verification.overall_confidence,
                research.fact_verification.fallback_used,
            )
            research_logger.info(
                "Research package complete topic=%s originality_score=%s chosen_angle=%s fallback_usage=%s",
                topic,
                research.competitor_analysis.originality_score,
                research.competitor_analysis.unique_video_angle,
                False,
            )
            return research
        except Exception:
            logger.exception("Structured research generation failed topic=%s; using fallback", topic)
            research_logger.exception(
                "Research package fallback topic=%s originality_score=%s chosen_angle=%s fallback_usage=%s",
                topic,
                competitor_analysis.originality_score,
                competitor_analysis.unique_video_angle,
                True,
            )
            research = self._fallback_research(topic, competitor_analysis)
            research.fact_verification = self.fact_verification_service.verify(research)
            return research

    def _fallback_research(self, topic: str, competitor_analysis: CompetitorAnalysis) -> ResearchResult:
        """Build a minimal research package so the pipeline can continue."""
        return ResearchResult(
            topic=topic,
            category="Technology",
            target_audience="Curious creators, professionals, and beginners",
            summary=f"{topic} is attracting attention because it can change how people work and create.",
            why_it_matters="People want practical ways to save time, learn faster, and make better content.",
            interesting_facts=[
                f"{topic} is being discussed by creators and technology communities.",
                "The most useful short videos focus on one practical takeaway.",
                "Clear examples and simple language make technical topics easier to understand.",
            ],
            statistics=[],
            misconceptions=[
                "New technology is not useful just because it is popular.",
            ],
            keywords=[topic, "technology", "productivity"],
            official_sources=[],
            video_angle=f"Explain one practical reason {topic} matters right now.",
            hook_ideas=[
                f"{topic} is changing faster than most people realize.",
                f"Here is the simple reason {topic} keeps showing up everywhere.",
                f"Most people miss the real story behind {topic}.",
            ],
            cta_ideas=[
                "Follow for more simple tech breakdowns.",
                "Comment what you want explained next.",
                "Save this if you want smarter tech updates.",
            ],
            competitor_analysis=competitor_analysis,
            fact_verification=None,
        )
