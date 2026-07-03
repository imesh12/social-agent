from pathlib import Path

from services.content_intelligence_service import AudienceRetentionAnalysis, ContentIntelligenceService
from services.llm.ollama_llm_service import OllamaLLMService
from tests.fake_llm import FakeLLMService


def test_successful_content_intelligence_analysis() -> None:
    llm = FakeLLMService()
    service = ContentIntelligenceService(llm_service=llm)

    result = service.analyze_audience_retention("Most people miss this. Here is why. Follow for more.")

    assert llm.content_intelligence_called is True
    assert result.overall_retention_score == 88
    assert result.drop_risk == "low"
    assert result.fallback_used is False


def test_content_intelligence_fallback_analysis() -> None:
    llm = FakeLLMService(fail_content_intelligence=True)
    service = ContentIntelligenceService(llm_service=llm)

    result = service.analyze_audience_retention("Most people miss this. Here is why. Follow for more.")

    assert result.fallback_used is True
    assert result.overall_retention_score > 0
    assert result.predicted_drop_points
    assert "add curiosity" in result.improvements


def test_content_intelligence_llm_response_parsing(monkeypatch) -> None:
    service = OllamaLLMService.__new__(OllamaLLMService)
    monkeypatch.setattr(service, "_load_prompt", lambda name: "{script}")
    monkeypatch.setattr(
        service,
        "_generate",
        lambda prompt: """
        {
          "overall_retention_score": 91,
          "opening_strength": 92,
          "first_5_seconds": 90,
          "curiosity_gap": 89,
          "story_flow": 88,
          "information_density": 85,
          "pace": 90,
          "emotional_trigger": 84,
          "ending_strength": 87,
          "drop_risk": "low",
          "predicted_drop_points": ["sentence 4"],
          "improvements": ["add pattern interrupt"],
          "strengths": ["strong hook"],
          "analysis_timestamp": "2026-06-30T00:00:00+00:00",
          "fallback_used": false
        }
        """,
    )

    result = service.analyze_content_intelligence("A strong script.")

    assert isinstance(result, AudienceRetentionAnalysis)
    assert result.overall_retention_score == 91
    assert result.predicted_drop_points == ["sentence 4"]


def test_content_intelligence_logging() -> None:
    service = ContentIntelligenceService(llm_service=FakeLLMService())

    service.analyze_audience_retention("Most people miss this. Here is why. Follow for more.")

    assert Path("storage/logs/content_intelligence.log").exists()
