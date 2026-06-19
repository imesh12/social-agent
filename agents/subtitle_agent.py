import logging

from sqlalchemy.orm import Session

from database.models import Subtitle, SubtitleStatus, Video
from services.subtitle_service import SubtitleService

logger = logging.getLogger(__name__)


class VideoNotFoundError(Exception):
    def __init__(self, video_id: int) -> None:
        super().__init__(f"Video {video_id} was not found")
        self.video_id = video_id


class SubtitleAgent:
    def __init__(self, db: Session, subtitle_service: SubtitleService) -> None:
        self.db = db
        self.subtitle_service = subtitle_service

    def generate_subtitles(self, video_id: int) -> Subtitle:
        video = self.db.get(Video, video_id)
        if video is None:
            logger.warning("Cannot generate subtitles because video_id=%s was not found", video_id)
            raise VideoNotFoundError(video_id)

        script = video.audio.script
        output_path = f"storage/subtitles/subtitle_{video.id}.srt"
        logger.info("Generating subtitles for video_id=%s", video.id)

        try:
            self.subtitle_service.generate_srt(
                script_text=script.content,
                output_path=output_path,
            )
            subtitle = Subtitle(video_id=video.id, path=output_path, status=SubtitleStatus.GENERATED)
            self.db.add(subtitle)
            self.db.commit()
            self.db.refresh(subtitle)
            logger.info("Generated subtitle id=%s video_id=%s path=%s", subtitle.id, video.id, subtitle.path)
            return subtitle
        except Exception:
            self.db.rollback()
            logger.exception("Subtitle generation failed for video_id=%s", video.id)
            raise
