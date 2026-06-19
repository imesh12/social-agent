import logging
from pathlib import Path

from sqlalchemy.orm import Session

from database.models import PublishJob, PublishJobStatus, Video
from services.youtube_service import YouTubeService

logger = logging.getLogger(__name__)


class PublishVideoNotFoundError(Exception):
    def __init__(self, video_id: int) -> None:
        super().__init__(f"Video {video_id} was not found")
        self.video_id = video_id


class PublishVideoFileNotFoundError(Exception):
    def __init__(self, video_path: str) -> None:
        super().__init__(f"Video file {video_path} was not found")
        self.video_path = video_path


class PublisherAgent:
    def __init__(self, db: Session, youtube_service: YouTubeService) -> None:
        self.db = db
        self.youtube_service = youtube_service

    def publish_youtube(self, video_id: int) -> PublishJob:
        video = self.db.get(Video, video_id)
        if video is None:
            logger.warning("Cannot publish because video_id=%s was not found", video_id)
            raise PublishVideoNotFoundError(video_id)

        if not Path(video.path).exists():
            logger.warning("Cannot publish because video file is missing: %s", video.path)
            raise PublishVideoFileNotFoundError(video.path)

        logger.info("Publishing video_id=%s to YouTube Shorts", video.id)
        try:
            result = self.youtube_service.upload_video(video_path=video.path)
            job = PublishJob(
                video_id=video.id,
                platform="youtube",
                youtube_video_id=result.youtube_video_id,
                youtube_url=result.youtube_url,
                status=PublishJobStatus.UPLOADED,
            )
            self.db.add(job)
            self.db.commit()
            self.db.refresh(job)
            logger.info("Published video_id=%s youtube_video_id=%s", video.id, job.youtube_video_id)
            return job
        except Exception:
            self.db.rollback()
            logger.exception("YouTube publish failed for video_id=%s", video.id)
            raise
