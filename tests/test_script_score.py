from services.llm.base_llm_service import ScriptScore
from services.llm.ollama_llm_service import OllamaLLMService


def test_script_score_json_parsing(monkeypatch) -> None:
    service = OllamaLLMService.__new__(OllamaLLMService)

    monkeypatch.setattr(service, "_load_prompt", lambda name: "{script}")
    monkeypatch.setattr(
        service,
        "_generate",
        lambda prompt: """
        {
          "hook": 93,
          "clarity": 91,
          "retention": 92,
          "storytelling": 90,
          "cta": 86,
          "overall": 91,
          "strengths": ["Strong hook"],
          "improvements": ["Tighten CTA"]
        }
        """,
    )

    score = service.score_script("A strong short script.")

    assert isinstance(score, ScriptScore)
    assert score.overall == 91
    assert score.score_summary()["hook"] == 93
