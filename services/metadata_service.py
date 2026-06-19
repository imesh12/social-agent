import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from database.models import SEO, Thumbnail, Video
from services.utils.logging import get_rotating_logger

metadata_logger = get_rotating_logger("system_health", "system_health.log")


class GenerationMetadataService:
    """Persist generation history as timestamped JSON files."""

    def __init__(self, output_dir: str = "storage/generated") -> None:
        self.output_dir = Path(output_dir)

    def save_metadata(self, metadata: dict[str, Any]) -> Path:
        """Save metadata to a timestamped JSON file and return the path."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        path = self.output_dir / f"{timestamp}.json"
        suffix = 1
        while path.exists():
            path = self.output_dir / f"{timestamp}_{suffix}.json"
            suffix += 1
        path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        (self.output_dir / "latest.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return path

    def save_for_video(self, db: Session, video_id: int, youtube_id: str | None = None) -> Path | None:
        """Build and save generation metadata for a video, logging failures."""
        try:
            video = db.get(Video, video_id)
            if video is None:
                raise ValueError(f"Video {video_id} was not found")

            script = video.audio.script
            seo = (
                db.query(SEO)
                .filter(SEO.video_id == video.id)
                .order_by(SEO.created_at.desc())
                .first()
            )
            thumbnail = (
                db.query(Thumbnail)
                .filter(Thumbnail.video_id == video.id)
                .order_by(Thumbnail.created_at.desc())
                .first()
            )
            metadata = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "topic": script.topic.title,
                "research": "",
                "script": script.content,
                "title": seo.title if seo else "",
                "description": seo.description if seo else "",
                "tags": json.loads(seo.tags) if seo else [],
                "thumbnail_path": thumbnail.path if thumbnail else "",
                "video_path": video.path,
                "youtube_id": youtube_id or "",
            }
            path = self.save_metadata(metadata)
            metadata_logger.info("Saved generation metadata path=%s video_id=%s", path, video_id)
            return path
        except Exception as exc:
            metadata_logger.exception("Metadata saving failure video_id=%s error=%s", video_id, exc)
            return None
