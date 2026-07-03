from pathlib import Path

from services.llm.ollama_llm_service import OllamaLLMService
from services.viral_prediction_service import ViralPredictionResult, ViralPredictionService
from tests.fake_llm import FakeLLMService


def prediction(score: int) -> ViralPredictionResult:
    return ViralPredictionResult(
        viral_score=score,
        predicted_ctr=score,
        predicted_retention=score,
        shareability="High" if score >= 90 else "Medium",
        uniqueness="High" if score >= 85 else "Medium",
        competition="Medium",
        emotion="curiosity",
        risk_level="Low" if score >= 80 else "High",
        confidence=82,
        publish_recommendation=True,
        reasons=["strong hook", "clear thumbnail"],
        improvements=[],
        analysis_timestamp="2026-06-30T00:00:00+00:00",
        fallback_used=False,
    )


def test_successful_viral_prediction() -> None:
    llm = FakeLLMService(viral_prediction=prediction(92))
    service = ViralPredictionService(llm_service=llm)

    result = service.predict({"script_score": {"overall": 90}})

    assert llm.viral_prediction_called is True
    assert result.viral_score == 92
    assert result.publish_recommendation is True


def test_low_score_viral_prediction_recommends_not_publish() -> None:
    service = ViralPredictionService(llm_service=FakeLLMService(viral_prediction=prediction(72)))

    result = service.predict({"script_score": {"overall": 72}})

    assert result.viral_score == 72
    assert result.publish_recommendation is False
    assert result.improvements


def test_mid_score_viral_prediction_recommends_publish_with_improvements() -> None:
    service = ViralPredictionService(llm_service=FakeLLMService(viral_prediction=prediction(84)))

    result = service.predict({"script_score": {"overall": 84}})

    assert result.publish_recommendation is True
    assert result.improvements


def test_viral_prediction_fallback_behavior() -> None:
    service = ViralPredictionService(llm_service=FakeLLMService(fail_viral_prediction=True))

    result = service.predict(
        {
            "script_score": {"overall": 78},
            "content_intelligence": {"overall_retention_score": 80},
            "thumbnail_intelligence": {"overall_score": 76},
            "seo_intelligence": {"overall_score": 82},
        }
    )

    assert result.fallback_used is True
    assert result.viral_score == 79
    assert result.confidence == 50


def test_viral_prediction_llm_response_parsing(monkeypatch) -> None:
    service = OllamaLLMService.__new__(OllamaLLMService)
    monkeypatch.setattr(service, "_load_prompt", lambda name: "{content_package}")
    monkeypatch.setattr(
        service,
        "_generate",
        lambda prompt: """
        {
          "viral_score": 91,
          "predicted_ctr": 88,
          "predicted_retention": 89,
          "shareability": "High",
          "uniqueness": "High",
          "competition": "Medium",
          "emotion": "curiosity",
          "risk_level": "Low",
          "confidence": 86,
          "publish_recommendation": true,
          "reasons": ["strong hook"],
          "improvements": ["increase emotional contrast"],
          "analysis_timestamp": "2026-06-30T00:00:00+00:00",
          "fallback_used": false
        }
        """,
    )

    result = service.analyze_viral_prediction({"script": "A short script."})

    assert isinstance(result, ViralPredictionResult)
    assert result.viral_score == 91
    assert result.publish_recommendation is True


def test_viral_prediction_logging() -> None:
    service = ViralPredictionService(llm_service=FakeLLMService())

    service.predict({"script_score": {"overall": 90}})

    assert Path("storage/logs/viral_prediction.log").exists()
