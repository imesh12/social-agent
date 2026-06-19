import time
from datetime import datetime, timezone
from pathlib import Path

from services.utils.logging import get_rotating_logger

cleanup_logger = get_rotating_logger("cleanup", "cleanup.log")


class CleanupService:
    """Delete generated transient files older than the configured retention window."""

    cleanup_dirs = (
        "storage/audio",
        "storage/videos",
        "storage/temp",
        "storage/subtitles",
    )

    def __init__(self, retention_days: int = 30, directories: tuple[str, ...] | None = None) -> None:
        self.retention_days = retention_days
        self.directories = directories or self.cleanup_dirs

    def cleanup_old_files(self) -> int:
        """Delete files older than retention_days and return the number removed."""
        started_at = time.perf_counter()
        cutoff_seconds = self.retention_days * 24 * 60 * 60
        now = time.time()
        deleted = 0

        try:
            for directory in self.directories:
                root = Path(directory)
                root.mkdir(parents=True, exist_ok=True)
                for path in root.rglob("*"):
                    if not path.is_file():
                        continue
                    age_seconds = now - path.stat().st_mtime
                    if age_seconds <= cutoff_seconds:
                        continue
                    try:
                        path.unlink()
                        deleted += 1
                        cleanup_logger.info(
                            "Deleted file path=%s age_days=%.2f",
                            path,
                            age_seconds / 86400,
                        )
                    except Exception as exc:
                        cleanup_logger.exception("Cleanup delete error path=%s error=%s", path, exc)
            cleanup_logger.info(
                "Cleanup complete deleted=%s execution_time=%.3fs timestamp=%s",
                deleted,
                time.perf_counter() - started_at,
                datetime.now(timezone.utc).isoformat(),
            )
            return deleted
        except Exception as exc:
            cleanup_logger.exception(
                "Cleanup execution error error=%s execution_time=%.3fs",
                exc,
                time.perf_counter() - started_at,
            )
            return deleted
