from pathlib import Path

from services.llm.base_llm_service import LLMSEOResult
from services.llm.ollama_llm_service import OllamaLLMService
from services.seo_intelligence_service import SEOIntelligenceResult, SEOIntelligenceService
from tests.fake_llm import FakeLLMService


def seo_result(title: str = "Top 3 AI Tools You Need In 2026 #shorts") -> LLMSEOResult:
    return LLMSEOResult(
        title=title,
        description="Discover AI tools changing productivity.",
        tags=["AI", "ChatGPT", "Technology"],
        hashtags="#ai #shorts #technology",
    )


def seo_score(score: int, attempt: int = 0, title: str = "Better AI Tools Title #shorts") -> SEOIntelligenceResult:
    return SEOIntelligenceResult(
        overall_score=score,
        title_score=score,
        description_score=score,
        keyword_score=score,
        tag_score=score,
        hashtag_score=score,
        search_intent_score=score,
        ctr_prediction=score,
        competition_level="medium",
        readability_score=score,
        engagement_score=score,
        recommended_title=title,
        recommended_description="Improved description for AI tools.",
        recommended_tags=["AI", "Tools", "Productivity"],
        recommended_hashtags="#ai #shorts #tools",
        strengths=["clear search intent"],
        weaknesses=["needs specificity"],
        recommended_changes=["make title more specific"],
        accepted=score >= 85,
        attempt=attempt,
        analysis_timestamp="2026-06-30T00:00:00+00:00",
        fallback_used=False,
    )


def test_successful_seo_intelligence_analysis() -> None:
    llm = FakeLLMService(seo_score_sequence=[seo_score(90)])
    service = SEOIntelligenceService(llm_service=llm)

    result = service.analyze_seo("AI tools script", seo_result(), attempt=0)

    assert llm.seo_intelligence_called is True
    assert result.overall_score == 90
    assert result.accepted is True


def test_seo_intelligence_fallback_behavior() -> None:
    service = SEOIntelligenceService(llm_service=FakeLLMService(fail_seo_intelligence=True))

    result = service.analyze_seo("AI tools script", seo_result(), attempt=1)

    assert result.fallback_used is True
    assert result.overall_score > 0
    assert result.recommended_changes


def test_seo_intelligence_regenerates_and_accepts_improved_package() -> None:
    improved = seo_result("Specific AI Workflow Tools For Creators #shorts")
    llm = FakeLLMService(
        seo_score_sequence=[seo_score(70), seo_score(91)],
        improved_seo_sequence=[improved],
    )
    service = SEOIntelligenceService(llm_service=llm)

    selection = service.optimize_seo("AI tools script", seo_result("Generic AI Tools"))

    assert llm.seo_improvement_calls == 1
    assert selection.seo.title == "Specific AI Workflow Tools For Creators #shorts"
    assert selection.intelligence.overall_score == 91
    assert selection.attempt_count == 2


def test_seo_intelligence_max_attempts_and_highest_score_selection() -> None:
    first = seo_result("First")
    second = seo_result("Second")
    third = seo_result("Third")
    llm = FakeLLMService(
        seo_score_sequence=[seo_score(70), seo_score(82), seo_score(75)],
        improved_seo_sequence=[second, third],
    )
    service = SEOIntelligenceService(llm_service=llm)

    selection = service.optimize_seo("AI tools script", first)

    assert llm.seo_intelligence_calls == 3
    assert selection.seo.title == "Second"
    assert selection.intelligence.overall_score == 82
    assert selection.intelligence.accepted is False
    assert selection.attempt_count == 2


def test_seo_intelligence_llm_response_parsing(monkeypatch) -> None:
    service = OllamaLLMService.__new__(OllamaLLMService)
    monkeypatch.setattr(service, "_load_prompt", lambda name: "{script_text} {seo_package}")
    monkeypatch.setattr(
        service,
        "_generate",
        lambda prompt: """
        {
          "overall_score": 91,
          "title_score": 90,
          "description_score": 89,
          "keyword_score": 88,
          "tag_score": 87,
          "hashtag_score": 86,
          "search_intent_score": 91,
          "ctr_prediction": 90,
          "competition_level": "medium",
          "readability_score": 92,
          "engagement_score": 85,
          "recommended_title": "Better AI Tools Title #shorts",
          "recommended_description": "Better description.",
          "recommended_tags": ["AI", "Tools"],
          "recommended_hashtags": "#ai #shorts",
          "strengths": ["clear"],
          "weaknesses": ["none"],
          "recommended_changes": ["tighten title"],
          "accepted": true,
          "attempt": 0,
          "analysis_timestamp": "2026-06-30T00:00:00+00:00",
          "fallback_used": false
        }
        """,
    )

    result = service.analyze_seo_intelligence("script", seo_result())

    assert isinstance(result, SEOIntelligenceResult)
    assert result.overall_score == 91
    assert result.recommended_title == "Better AI Tools Title #shorts"


def test_seo_intelligence_logging() -> None:
    service = SEOIntelligenceService(llm_service=FakeLLMService())

    service.analyze_seo("AI tools script", seo_result(), attempt=0)

    assert Path("storage/logs/seo_intelligence.log").exists()
