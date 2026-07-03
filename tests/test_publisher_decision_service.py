from pathlib import Path

from services.llm.ollama_llm_service import OllamaLLMService
from services.publisher_decision_service import PublisherDecisionResult, PublisherDecisionService
from tests.fake_llm import FakeLLMService


def decision(score: int) -> PublisherDecisionResult:
    return PublisherDecisionResult(
        publish=True,
        confidence=86,
        overall_score=score,
        expected_views=2500 if score >= 80 else 300,
        expected_ctr=score,
        expected_retention=score,
        risk_level="Low" if score >= 90 else "Medium" if score >= 80 else "High",
        strengths=["strong hook"],
        weaknesses=["minor risk"],
        improvements=[],
        recommended_publish_time="18:00",
        recommended_day="Friday",
        reasoning="Score-based test decision.",
        analysis_timestamp="2026-06-30T00:00:00+00:00",
        fallback_used=False,
    )


def test_successful_publisher_decision() -> None:
    llm = FakeLLMService(publisher_decision=decision(91))
    service = PublisherDecisionService(llm_service=llm)

    result = service.decide({"viral_prediction": {"viral_score": 91}})

    assert llm.publisher_decision_called is True
    assert result.overall_score == 91
    assert result.publish is True


def test_low_score_publisher_decision_recommends_not_publish() -> None:
    service = PublisherDecisionService(llm_service=FakeLLMService(publisher_decision=decision(72)))

    result = service.decide({"viral_prediction": {"viral_score": 72}})

    assert result.overall_score == 72
    assert result.publish is False
    assert result.improvements


def test_high_score_publisher_decision_recommends_publish() -> None:
    service = PublisherDecisionService(llm_service=FakeLLMService(publisher_decision=decision(94)))

    result = service.decide({"viral_prediction": {"viral_score": 94}})

    assert result.publish is True
    assert result.risk_level == "Low"


def test_publisher_decision_fallback_behavior() -> None:
    service = PublisherDecisionService(llm_service=FakeLLMService(fail_publisher_decision=True))

    result = service.decide(
        {
            "script_score": {"overall": 82},
            "content_intelligence": {"overall_retention_score": 80},
            "thumbnail_intelligence": {"overall_score": 78, "ctr_prediction": 76},
            "seo_intelligence": {"overall_score": 84},
            "viral_prediction": {"viral_score": 79, "predicted_ctr": 75, "predicted_retention": 80},
        }
    )

    assert result.fallback_used is True
    assert result.overall_score == 81
    assert result.publish is True
    assert result.expected_ctr == 75


def test_publisher_decision_llm_response_parsing(monkeypatch) -> None:
    service = OllamaLLMService.__new__(OllamaLLMService)
    monkeypatch.setattr(service, "_load_prompt", lambda name: "{content_package}")
    monkeypatch.setattr(
        service,
        "_generate",
        lambda prompt: """
        {
          "publish": true,
          "confidence": 88,
          "overall_score": 91,
          "expected_views": 2500,
          "expected_ctr": 87,
          "expected_retention": 89,
          "risk_level": "Low",
          "strengths": ["strong hook"],
          "weaknesses": ["minor thumbnail risk"],
          "improvements": ["tighten thumbnail text"],
          "recommended_publish_time": "18:00",
          "recommended_day": "Friday",
          "reasoning": "Strong package.",
          "analysis_timestamp": "2026-06-30T00:00:00+00:00",
          "fallback_used": false
        }
        """,
    )

    result = service.analyze_publisher_decision({"script": "A short script."})

    assert isinstance(result, PublisherDecisionResult)
    assert result.overall_score == 91
    assert result.publish is True


def test_publisher_decision_logging() -> None:
    service = PublisherDecisionService(llm_service=FakeLLMService())

    service.decide({"viral_prediction": {"viral_score": 91}})

    assert Path("storage/logs/publisher_decision.log").exists()
