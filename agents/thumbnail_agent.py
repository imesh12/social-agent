import logging

from sqlalchemy.orm import Session

from database.models import Thumbnail, Video
from services.thumbnail_service import ThumbnailService

logger = logging.getLogger(__name__)


class ThumbnailVideoNotFoundError(Exception):
    def __init__(self, video_id: int) -> None:
        super().__init__(f"Video {video_id} was not found")
        self.video_id = video_id


class ThumbnailAgent:
    def __init__(self, db: Session, thumbnail_service: ThumbnailService) -> None:
        self.db = db
        self.thumbnail_service = thumbnail_service

    def generate_thumbnail(self, video_id: int) -> Thumbnail:
        video = self.db.get(Video, video_id)
        if video is None:
            logger.warning("Cannot generate thumbnail because video_id=%s was not found", video_id)
            raise ThumbnailVideoNotFoundError(video_id)

        output_path = f"storage/thumbnails/thumb_{video.id}.jpg"
        logger.info("Generating thumbnail for video_id=%s", video.id)

        try:
            self.thumbnail_service.generate_thumbnail(output_path=output_path)
            thumbnail = Thumbnail(video_id=video.id, path=output_path)
            self.db.add(thumbnail)
            self.db.commit()
            self.db.refresh(thumbnail)
            logger.info("Generated thumbnail id=%s video_id=%s path=%s", thumbnail.id, video.id, thumbnail.path)
            return thumbnail
        except Exception:
            self.db.rollback()
            logger.exception("Thumbnail generation failed for video_id=%s", video.id)
            raise
