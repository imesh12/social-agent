from agents.research_agent import ResearchResult
from agents.script_agent import ScriptAgent
from services.content_intelligence_service import AudienceRetentionAnalysis
from services.fact_verification_service import ClaimVerificationDetail, FactVerificationResult
from services.hook_intelligence_service import HookCandidate, HookSelection
from services.llm.base_llm_service import ScriptScore, ScriptVariant, ScriptVariants
from tests.fake_llm import FakeLLMService


def make_research_result() -> ResearchResult:
    return ResearchResult(
        topic="AI Tools",
        category="Technology",
        target_audience="Creators",
        summary="AI tools help creators move faster.",
        why_it_matters="Creators can save time on repetitive work.",
        interesting_facts=[
            "AI tools help creators move faster.",
            "Automation can support writing, editing, and repurposing.",
            "Short examples make AI workflows easier to understand.",
        ],
        statistics=[],
        misconceptions=["AI tools still need human judgment."],
        keywords=["AI", "tools", "productivity"],
        official_sources=[],
        video_angle="Explain one simple AI workflow creators can use today.",
        hook_ideas=[
            "These AI tools are changing everything.",
            "Most creators miss this AI shortcut.",
            "This is the simplest AI workflow to try.",
        ],
        cta_ideas=[
            "Which one would you try?",
            "Follow for more simple AI tips.",
            "Save this for your next workflow.",
        ],
    )


def test_script_agent_calls_review_script() -> None:
    llm = FakeLLMService(reviewed_script='Hook:\n"Stop scrolling. These tools matter."\n\nEnding:\n"Follow for more."')
    agent = ScriptAgent(llm_service=llm)

    result = agent.create_script(make_research_result())

    assert llm.review_called is True
    assert result.content == 'Hook:\n"Stop scrolling. These tools matter."\n\nEnding:\n"Follow for more."'


def test_script_agent_falls_back_to_draft_when_review_fails() -> None:
    llm = FakeLLMService(fail_review=True)
    agent = ScriptAgent(llm_service=llm)

    result = agent.create_script(make_research_result())

    assert llm.review_called is True
    assert "These AI tools are changing everything" in result.content


def test_script_agent_consumes_structured_research_package() -> None:
    llm = FakeLLMService()
    agent = ScriptAgent(llm_service=llm)
    research = make_research_result()

    agent.create_script(research)

    assert llm.last_script_research is not None
    assert llm.last_script_research.topic == research.topic
    assert llm.last_script_research.video_angle == "Explain one simple AI workflow creators can use today."
    assert llm.last_script_research.selected_hook


def score(overall: int) -> ScriptScore:
    return ScriptScore(
        hook=overall,
        clarity=overall,
        retention=overall,
        storytelling=overall,
        cta=overall,
        overall=overall,
        strengths=["Useful structure"],
        improvements=["Tighten pacing"],
    )


class FixedHookIntelligenceService:
    def __init__(self) -> None:
        self.called = False
        self.hook = HookCandidate(
            text="Most people miss the practical side of AI tools.",
            type="Curiosity",
            emotion="intrigue",
            curiosity_score=90,
            clarity_score=88,
            novelty_score=86,
            retention_score=91,
            overall_score=89,
            reasoning="Strong hook.",
        )

    def generate_hooks(self, research_package: ResearchResult) -> HookSelection:
        self.called = True
        return HookSelection(
            candidates=[self.hook],
            selected_hook=self.hook,
            selection_reason="Highest scoring hook.",
            generation_time=0.01,
            fallback_used=False,
        )


class FixedContentIntelligenceService:
    def __init__(self) -> None:
        self.called = False
        self.last_script = ""

    def analyze_audience_retention(self, script: str) -> AudienceRetentionAnalysis:
        self.called = True
        self.last_script = script
        return AudienceRetentionAnalysis(
            overall_retention_score=93,
            opening_strength=94,
            first_5_seconds=92,
            curiosity_gap=91,
            story_flow=90,
            information_density=88,
            pace=89,
            emotional_trigger=86,
            ending_strength=87,
            drop_risk="low",
            predicted_drop_points=["sentence 4"],
            improvements=["add pattern interrupt"],
            strengths=["strong opening"],
            analysis_timestamp="2026-06-30T00:00:00+00:00",
            fallback_used=False,
        )


def test_high_script_score_is_accepted_immediately() -> None:
    llm = FakeLLMService(score_sequence=[score(91)])
    agent = ScriptAgent(llm_service=llm)

    result = agent.create_script(make_research_result())

    assert result.score is not None
    assert result.score.overall == 91
    assert result.accepted is True
    assert result.regenerated is False
    assert result.attempt_count == 1
    assert llm.generate_script_calls == 1


def test_low_script_score_regenerates() -> None:
    llm = FakeLLMService(score_sequence=[score(70), score(89)])
    agent = ScriptAgent(llm_service=llm)

    result = agent.create_script(make_research_result())

    assert result.score is not None
    assert result.score.overall == 89
    assert result.accepted is True
    assert result.regenerated is True
    assert result.attempt_count == 2
    assert llm.generate_script_calls == 2


def test_maximum_regeneration_attempts_are_respected() -> None:
    llm = FakeLLMService(score_sequence=[score(40), score(50), score(60), score(95)])
    agent = ScriptAgent(llm_service=llm)

    result = agent.create_script(make_research_result())

    assert result.score is not None
    assert result.score.overall == 60
    assert result.accepted is False
    assert result.regenerated is True
    assert result.attempt_count == 3
    assert llm.generate_script_calls == 3


def test_highest_scoring_script_is_selected_after_final_attempt() -> None:
    drafts = ["draft one", "draft two is best", "draft three"]
    llm = FakeLLMService(
        score_sequence=[score(55), score(80), score(65)],
        script_drafts=drafts,
    )
    agent = ScriptAgent(llm_service=llm)

    result = agent.create_script(make_research_result())

    assert result.content == "draft two is best"
    assert result.score is not None
    assert result.score.overall == 80
    assert result.accepted is False
    assert result.attempt_count == 3


def test_scoring_failure_accepts_reviewed_script() -> None:
    llm = FakeLLMService(fail_score=True)
    agent = ScriptAgent(llm_service=llm)

    result = agent.create_script(make_research_result())

    assert llm.score_called is True
    assert result.score is None
    assert result.accepted is True
    assert result.regenerated is False
    assert result.attempt_count == 1
    assert "These AI tools are changing everything" in result.content


def test_script_agent_uses_verified_claims_and_removes_rejected_claims() -> None:
    llm = FakeLLMService()
    agent = ScriptAgent(llm_service=llm)
    research = make_research_result()
    rejected = "AI tools are guaranteed to improve output by 90 percent."
    verified = "AI tools help creators move faster."
    research.interesting_facts = [
        verified,
        rejected,
        "Automation can support writing, editing, and repurposing.",
    ]
    research.fact_verification = FactVerificationResult(
        verified_claims=[verified],
        rejected_claims=[rejected],
        verification_summary="Rejected unsupported statistic.",
        overall_confidence=82,
        sources_checked=["OpenAI"],
        verification_time=0.01,
        fallback_used=False,
        claim_details=[
            ClaimVerificationDetail(
                claim=verified,
                status="verified",
                confidence=90,
                source="OpenAI",
                notes="Matched source.",
            ),
            ClaimVerificationDetail(
                claim=rejected,
                status="rejected",
                confidence=30,
                source="",
                notes="Unsupported statistic.",
            ),
        ],
    )

    agent.create_script(research)

    assert llm.last_script_research is not None
    assert verified in llm.last_script_research.interesting_facts
    assert rejected not in llm.last_script_research.interesting_facts
    assert rejected not in llm.last_script_research.statistics


def test_script_agent_passes_selected_hook_to_script_generation() -> None:
    llm = FakeLLMService()
    hook_service = FixedHookIntelligenceService()
    agent = ScriptAgent(llm_service=llm, hook_intelligence_service=hook_service)

    result = agent.create_script(make_research_result())

    assert hook_service.called is True
    assert result.hook_selection is not None
    assert result.hook_selection.selected_hook.text == "Most people miss the practical side of AI tools."
    assert llm.last_script_research is not None
    assert llm.last_script_research.selected_hook == "Most people miss the practical side of AI tools."
    assert llm.last_script_research.top_hooks == ["Most people miss the practical side of AI tools."]
    assert llm.last_script_research.selection_reason == "Highest scoring hook."


def test_script_agent_runs_content_intelligence_after_final_script() -> None:
    llm = FakeLLMService(reviewed_script="Most people miss this. Here is the useful part. Follow for more.")
    content_service = FixedContentIntelligenceService()
    agent = ScriptAgent(
        llm_service=llm,
        hook_intelligence_service=FixedHookIntelligenceService(),
        content_intelligence_service=content_service,
    )

    result = agent.create_script(make_research_result())

    assert content_service.called is True
    assert content_service.last_script == result.content
    assert result.content_intelligence is not None
    assert result.content_intelligence.overall_retention_score == 93


def test_script_agent_generates_and_selects_best_variant() -> None:
    variants = ScriptVariants(
        version_a=ScriptVariant(focus="High curiosity", script="Version A script."),
        version_b=ScriptVariant(focus="Storytelling", script="Version B script."),
        version_c=ScriptVariant(focus="Fast educational delivery", script="Version C script."),
    )
    llm = FakeLLMService(
        fail_script_variants=False,
        script_variants=variants,
        score_sequence=[score(80), score(95), score(89)],
    )
    agent = ScriptAgent(
        llm_service=llm,
        hook_intelligence_service=FixedHookIntelligenceService(),
        content_intelligence_service=FixedContentIntelligenceService(),
    )

    result = agent.create_script(make_research_result())

    assert llm.generate_script_variants_called is True
    assert result.version_selection is not None
    assert result.version_selection.winner == "B"
    assert result.version_selection.scores["B"] > result.version_selection.scores["A"]
    assert result.content == "Version B script."
    assert result.attempt_count == 3


def test_script_agent_falls_back_when_variant_generation_fails() -> None:
    llm = FakeLLMService(fail_script_variants=True)
    agent = ScriptAgent(llm_service=llm)

    result = agent.create_script(make_research_result())

    assert llm.generate_script_variants_called is True
    assert llm.generate_script_calls == 1
    assert result.version_selection is None
    assert "These AI tools are changing everything" in result.content
