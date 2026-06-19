import os
import time
from pathlib import Path

from services.cleanup_service import CleanupService


def test_cleanup_deletes_only_old_files(tmp_path: Path) -> None:
    audio_dir = tmp_path / "audio"
    video_dir = tmp_path / "videos"
    logs_dir = tmp_path / "logs"
    audio_dir.mkdir()
    video_dir.mkdir()
    logs_dir.mkdir()

    old_file = audio_dir / "old.mp3"
    fresh_file = video_dir / "fresh.mp4"
    protected_log = logs_dir / "old.log"
    old_file.write_text("old", encoding="utf-8")
    fresh_file.write_text("fresh", encoding="utf-8")
    protected_log.write_text("log", encoding="utf-8")

    old_timestamp = time.time() - (31 * 24 * 60 * 60)
    os.utime(old_file, (old_timestamp, old_timestamp))
    os.utime(protected_log, (old_timestamp, old_timestamp))

    service = CleanupService(retention_days=30, directories=(str(audio_dir), str(video_dir)))

    deleted = service.cleanup_old_files()

    assert deleted == 1
    assert not old_file.exists()
    assert fresh_file.exists()
    assert protected_log.exists()
