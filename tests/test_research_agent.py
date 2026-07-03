from agents.research_agent import ResearchAgent, ResearchResult
from services.competitor_analysis_service import CompetitorAnalysis
from services.fact_verification_service import ClaimVerificationDetail, FactVerificationResult
from tests.fake_llm import FakeLLMService


class FixedCompetitorAnalysisService:
    def __init__(self) -> None:
        self.called = False
        self.analysis = CompetitorAnalysis(
            searched_topic="AI Tools",
            competitor_titles=["Top AI tools for creators"],
            common_angles=["tool list or roundup"],
            repeated_keywords=["tools"],
            missing_angles=["Show a practical workflow."],
            unique_video_angle="Show a practical AI workflow competitors ignore.",
            hook_opportunities=["Most AI tool videos skip the workflow."],
            credibility_notes=["Use titles as directional signals."],
            originality_score=93,
        )

    def analyze(self, topic: str) -> CompetitorAnalysis:
        self.called = True
        return self.analysis


class FixedFactVerificationService:
    def __init__(self) -> None:
        self.called = False
        self.result = FactVerificationResult(
            verified_claims=["AI tools help creators move faster."],
            rejected_claims=["AI tools guarantee success."],
            verification_summary="One claim verified, one rejected.",
            overall_confidence=87,
            sources_checked=["OpenAI"],
            verification_time=0.01,
            fallback_used=False,
            claim_details=[
                ClaimVerificationDetail(
                    claim="AI tools help creators move faster.",
                    status="verified",
                    confidence=87,
                    source="OpenAI",
                    notes="Matched source.",
                )
            ],
        )

    def verify(self, research_package: ResearchResult) -> FactVerificationResult:
        self.called = True
        return self.result


def test_research_agent_generates_structured_package() -> None:
    competitor_service = FixedCompetitorAnalysisService()
    verification_service = FixedFactVerificationService()
    agent = ResearchAgent(
        llm_service=FakeLLMService(),
        competitor_analysis_service=competitor_service,
        fact_verification_service=verification_service,
    )

    result = agent.research_topic("AI Tools")

    assert competitor_service.called is True
    assert verification_service.called is True
    assert result.topic == "AI Tools"
    assert result.category == "Technology"
    assert result.competitor_analysis is not None
    assert result.competitor_analysis.originality_score == 93
    assert result.competitor_analysis.unique_video_angle == "Show a practical AI workflow competitors ignore."
    assert result.fact_verification is not None
    assert result.fact_verification.overall_confidence == 87
    assert len(result.interesting_facts) == 3
    assert len(result.hook_ideas) == 3
    assert len(result.cta_ideas) == 3
    assert result.facts == result.interesting_facts


def test_research_agent_falls_back_when_structured_generation_fails() -> None:
    competitor_service = FixedCompetitorAnalysisService()
    verification_service = FixedFactVerificationService()
    agent = ResearchAgent(
        llm_service=FakeLLMService(fail_research=True),
        competitor_analysis_service=competitor_service,
        fact_verification_service=verification_service,
    )

    result = agent.research_topic("AI Tools")

    assert result.topic == "AI Tools"
    assert result.category == "Technology"
    assert len(result.interesting_facts) == 3
    assert len(result.hook_ideas) == 3
    assert len(result.cta_ideas) == 3
    assert result.competitor_analysis is not None
    assert result.competitor_analysis.originality_score == 93
    assert result.fact_verification is not None
    assert result.fact_verification.overall_confidence == 87


def test_research_package_serialization_round_trip() -> None:
    result = ResearchAgent(llm_service=FakeLLMService()).research_topic("AI Tools")

    restored = ResearchResult.model_validate_json(result.model_dump_json())

    assert restored == result
    assert restored.video_angle == result.video_angle
