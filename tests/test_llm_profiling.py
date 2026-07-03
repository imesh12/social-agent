import json
from pathlib import Path

from services.llm.ollama_llm_service import OllamaLLMService
from services.llm.profiling import profile_operation


def test_llm_profile_logs_json_parse_metrics() -> None:
    """LLM profiling should record parse metrics without changing parse behavior."""
    log_path = Path("storage/logs/llm_profile.log")
    before_size = log_path.stat().st_size if log_path.exists() else 0
    service = OllamaLLMService()

    with profile_operation("test_parse", "test_prompt.txt", "Return JSON"):
        parsed = service._parse_json('{"ok": true}')

    assert parsed == {"ok": True}
    assert log_path.exists()
    new_content = log_path.read_text(encoding="utf-8")[before_size:]
    assert "llm_json_parse_completed" in new_content
    assert '"operation_name": "test_parse"' in new_content


def test_profile_operation_failure_logs_exception() -> None:
    """Failed LLM operations should emit structured failure metadata."""
    log_path = Path("storage/logs/llm_profile.log")
    before_size = log_path.stat().st_size if log_path.exists() else 0

    try:
        with profile_operation("test_failure", "test_prompt.txt", "Return JSON"):
            raise ValueError("profile failure")
    except ValueError:
        pass

    new_content = log_path.read_text(encoding="utf-8")[before_size:]
    assert "llm_operation_failed" in new_content
    assert '"exception_type": "ValueError"' in new_content
    assert json.loads(new_content.split("llm_operation_failed ", 1)[1].splitlines()[0])["status"] == "error"
