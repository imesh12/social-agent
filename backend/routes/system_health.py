import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Request

from backend.config import get_settings
from services.utils.logging import get_rotating_logger
from services.youtube_service import YouTubeService

router = APIRouter()
health_logger = get_rotating_logger("system_health", "system_health.log")


@router.get("/system-health")
def system_health(request: Request) -> dict[str, Any]:
    """Return fail-soft health information for local system dependencies."""
    settings = get_settings()
    payload: dict[str, Any] = {
        "status": "ok",
        "ollama": "error",
        "scheduler": "stopped",
        "youtube": "error",
        "disk_usage": "0%",
        "free_space_gb": 0,
        "model": settings.ollama_model,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        payload["ollama"] = _check_ollama(settings.ollama_base_url, settings.ollama_model)
    except Exception as exc:
        health_logger.exception("Ollama health check failed: %s", exc)
        payload["ollama"] = "error"

    try:
        scheduler = getattr(request.app.state, "scheduler", None)
        payload["scheduler"] = "ok" if scheduler and scheduler.running else "stopped"
    except Exception as exc:
        health_logger.exception("Scheduler health check failed: %s", exc)
        payload["scheduler"] = "stopped"

    try:
        payload["youtube"] = "ok" if YouTubeService().validate_credentials() else "error"
    except Exception as exc:
        health_logger.exception("YouTube health check failed: %s", exc)
        payload["youtube"] = "error"

    try:
        usage = shutil.disk_usage(Path("storage").resolve())
        used_percent = round((usage.used / usage.total) * 100)
        payload["disk_usage"] = f"{used_percent}%"
        payload["free_space_gb"] = round(usage.free / (1024**3))
    except Exception as exc:
        health_logger.exception("Disk health check failed: %s", exc)

    if any(payload[key] == "error" for key in ("ollama", "youtube")) or payload["scheduler"] != "ok":
        payload["status"] = "degraded"

    health_logger.info("System health check payload=%s", payload)
    return payload


def _check_ollama(base_url: str, model: str) -> str:
    with httpx.Client(timeout=2.0) as client:
        response = client.get(f"{base_url.rstrip('/')}/api/tags")
        response.raise_for_status()
        models = response.json().get("models", [])
    names = {str(item.get("name", "")) for item in models}
    return "ok" if model in names else "error"
