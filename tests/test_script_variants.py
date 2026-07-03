from services.llm.base_llm_service import ScriptVariants
from services.llm.ollama_llm_service import OllamaLLMService
from tests.test_script_agent import make_research_result


def test_script_variant_json_parsing(monkeypatch) -> None:
    service = OllamaLLMService.__new__(OllamaLLMService)
    monkeypatch.setattr(service, "_load_prompt", lambda name: "{research_package}")
    monkeypatch.setattr(
        service,
        "_generate",
        lambda prompt: """
        {
          "version_a": {
            "focus": "High curiosity",
            "script": "Curiosity script."
          },
          "version_b": {
            "focus": "Storytelling",
            "script": "Story script."
          },
          "version_c": {
            "focus": "Fast educational delivery",
            "script": "Fast script."
          }
        }
        """,
    )

    variants = service.generate_script_variants(make_research_result())

    assert isinstance(variants, ScriptVariants)
    assert variants.version_a.focus == "High curiosity"
    assert variants.version_b.script == "Story script."
