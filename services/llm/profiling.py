import contextlib
import ctypes
import json
import os
import shutil
import subprocess
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator

from services.utils.logging import get_rotating_logger

llm_profile_logger = get_rotating_logger("llm_profile", "llm_profile.log")


@dataclass
class LLMProfileContext:
    """Runtime profiling context for one logical LLM operation."""

    operation_name: str
    prompt_template: str
    prompt_characters: int
    estimated_prompt_tokens: int
    call_id: str
    started_at: float
    retry_attempt: int = 0


_current_context: ContextVar[LLMProfileContext | None] = ContextVar("llm_profile_context", default=None)


def estimate_tokens(text: str) -> int:
    """Return a cheap token estimate suitable for comparative profiling."""
    return max(1, round(len(text) / 4)) if text else 0


@contextlib.contextmanager
def profile_operation(operation_name: str, prompt_template: str, prompt: str) -> Iterator[LLMProfileContext]:
    """Attach operation metadata to all nested Ollama generation and JSON parsing logs."""
    context = LLMProfileContext(
        operation_name=operation_name,
        prompt_template=prompt_template,
        prompt_characters=len(prompt),
        estimated_prompt_tokens=estimate_tokens(prompt),
        call_id=str(uuid.uuid4()),
        started_at=time.perf_counter(),
    )
    token = _current_context.set(context)
    try:
        yield context
        log_profile_event(
            "llm_operation_completed",
            context=context,
            total_operation_duration_seconds=time.perf_counter() - context.started_at,
            status="success",
        )
    except Exception as exc:
        log_profile_event(
            "llm_operation_failed",
            context=context,
            total_operation_duration_seconds=time.perf_counter() - context.started_at,
            status="error",
            exception_type=type(exc).__name__,
            exception_message=str(exc),
        )
        raise
    finally:
        _current_context.reset(token)


def current_context() -> LLMProfileContext | None:
    """Return the active LLM profiling context, if any."""
    return _current_context.get()


def next_retry_attempt() -> int:
    """Increment and return the current retry attempt for the active operation."""
    context = current_context()
    if context is None:
        return 1
    context.retry_attempt += 1
    return context.retry_attempt


def log_profile_event(event: str, **payload: Any) -> None:
    """Write one structured JSON line to the dedicated LLM profile log."""
    context = payload.pop("context", None) or current_context()
    if context is not None:
        payload = {
            "call_id": context.call_id,
            "operation_name": context.operation_name,
            "prompt_template": context.prompt_template,
            "prompt_characters": context.prompt_characters,
            "estimated_prompt_tokens": context.estimated_prompt_tokens,
            "retry_attempt": context.retry_attempt,
            **payload,
        }
    llm_profile_logger.info("%s %s", event, json.dumps(payload, sort_keys=True, default=str))


def process_memory_bytes() -> int | None:
    """Return current process RSS where the platform exposes it without extra dependencies."""
    try:
        import psutil  # type: ignore

        return int(psutil.Process(os.getpid()).memory_info().rss)
    except Exception:
        pass

    if os.name == "nt":
        return _windows_process_memory_bytes()
    return _posix_process_memory_bytes()


def system_cpu_percent() -> float | None:
    """Return a best-effort system CPU percentage when psutil is available."""
    try:
        import psutil  # type: ignore

        value = psutil.cpu_percent(interval=None)
        return float(value)
    except Exception:
        return None


def gpu_snapshot() -> dict[str, Any] | None:
    """Return GPU utilization and VRAM from nvidia-smi when present."""
    if shutil.which("nvidia-smi") is None:
        return None
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except Exception as exc:
        return {"available": False, "error": str(exc)}
    if result.returncode != 0:
        return {"available": False, "error": result.stderr.strip()}

    devices: list[dict[str, int]] = []
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 3:
            continue
        try:
            devices.append(
                {
                    "gpu_utilization_percent": int(parts[0]),
                    "vram_used_mb": int(parts[1]),
                    "vram_total_mb": int(parts[2]),
                }
            )
        except ValueError:
            continue
    return {"available": True, "devices": devices}


def _windows_process_memory_bytes() -> int | None:
    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    try:
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        success = ctypes.windll.psapi.GetProcessMemoryInfo(
            handle,
            ctypes.byref(counters),
            counters.cb,
        )
        if not success:
            return None
        return int(counters.WorkingSetSize)
    except Exception:
        return None


def _posix_process_memory_bytes() -> int | None:
    try:
        with open("/proc/self/statm", encoding="utf-8") as file:
            resident_pages = int(file.read().split()[1])
        return resident_pages * os.sysconf("SC_PAGE_SIZE")
    except Exception:
        return None
