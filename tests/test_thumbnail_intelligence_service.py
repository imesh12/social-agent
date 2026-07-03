from pathlib import Path

from services.llm.ollama_llm_service import OllamaLLMService
from services.thumbnail_intelligence_service import ThumbnailIntelligenceResult, ThumbnailIntelligenceService
from tests.fake_llm import FakeLLMService


def thumbnail_score(score: int, attempt: int = 0) -> ThumbnailIntelligenceResult:
    return ThumbnailIntelligenceResult(
        overall_score=score,
        ctr_prediction=score,
        curiosity_score=score,
        emotion_score=score,
        contrast_score=score,
        visual_clarity=score,
        mobile_visibility=score,
        text_readability=score,
        subject_focus=score,
        brand_consistency=score,
        recommended_changes=["increase subject focus"],
        strengths=["clear text"],
        weaknesses=["needs more contrast"],
        regeneration_attempt=attempt,
        accepted=score >= 85,
        selected_thumbnail_path="",
        analysis_timestamp="2026-06-30T00:00:00+00:00",
        fallback_used=False,
    )


def test_successful_thumbnail_intelligence_analysis(tmp_path: Path) -> None:
    image_path = tmp_path / "thumb.jpg"
    image_path.write_bytes(b"fake-image")
    service = ThumbnailIntelligenceService(llm_service=FakeLLMService(thumbnail_score_sequence=[thumbnail_score(90)]))

    result = service.analyze_thumbnail(str(image_path), attempt=0)

    assert result.overall_score == 90
    assert result.accepted is True
    assert result.selected_thumbnail_path == str(image_path)


def test_thumbnail_intelligence_fallback_behavior(tmp_path: Path) -> None:
    image_path = tmp_path / "thumb.jpg"
    image_path.write_bytes(b"fake-image")
    service = ThumbnailIntelligenceService(llm_service=FakeLLMService(fail_thumbnail_intelligence=True))

    result = service.analyze_thumbnail(str(image_path), attempt=1)

    assert result.fallback_used is True
    assert result.regeneration_attempt == 1
    assert result.recommended_changes


def test_thumbnail_intelligence_llm_response_parsing(monkeypatch) -> None:
    service = OllamaLLMService.__new__(OllamaLLMService)
    monkeypatch.setattr(service, "_load_prompt", lambda name: "{thumbnail_path}")
    monkeypatch.setattr(
        service,
        "_generate",
        lambda prompt: """
        {
          "overall_score": 91,
          "ctr_prediction": 90,
          "curiosity_score": 89,
          "emotion_score": 88,
          "contrast_score": 92,
          "visual_clarity": 91,
          "mobile_visibility": 90,
          "text_readability": 93,
          "subject_focus": 87,
          "brand_consistency": 84,
          "recommended_changes": ["use four words or fewer"],
          "strengths": ["clear text"],
          "weaknesses": ["subject could be stronger"],
          "regeneration_attempt": 0,
          "accepted": true,
          "selected_thumbnail_path": "storage/thumbnails/thumb_1.jpg",
          "analysis_timestamp": "2026-06-30T00:00:00+00:00",
          "fallback_used": false
        }
        """,
    )

    result = service.analyze_thumbnail_intelligence("storage/thumbnails/thumb_1.jpg")

    assert isinstance(result, ThumbnailIntelligenceResult)
    assert result.overall_score == 91
    assert result.text_readability == 93


def test_thumbnail_intelligence_logging(tmp_path: Path) -> None:
    image_path = tmp_path / "thumb.jpg"
    image_path.write_bytes(b"fake-image")
    service = ThumbnailIntelligenceService(llm_service=FakeLLMService())

    service.analyze_thumbnail(str(image_path), attempt=0)

    assert Path("storage/logs/thumbnail_intelligence.log").exists()
