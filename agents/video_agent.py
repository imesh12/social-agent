import logging
from pathlib import Path

from sqlalchemy.orm import Session

from database.models import Audio, Video, VideoStatus
from services.ffmpeg_service import FFmpegService
from services.image_service import ImageService

logger = logging.getLogger(__name__)


class AudioNotFoundError(Exception):
    def __init__(self, audio_id: int) -> None:
        super().__init__(f"Audio {audio_id} was not found")
        self.audio_id = audio_id


class AudioFileNotFoundError(Exception):
    def __init__(self, audio_path: str) -> None:
        super().__init__(f"Audio file {audio_path} was not found")
        self.audio_path = audio_path


class VideoAgent:
    def __init__(
        self,
        db: Session,
        ffmpeg_service: FFmpegService,
        image_service: ImageService,
    ) -> None:
        self.db = db
        self.ffmpeg_service = ffmpeg_service
        self.image_service = image_service

    def generate_video(self, audio_id: int) -> Video:
        audio = self.db.get(Audio, audio_id)
        if audio is None:
            logger.warning("Cannot generate video because audio_id=%s was not found", audio_id)
            raise AudioNotFoundError(audio_id)

        if not Path(audio.path).exists():
            logger.warning("Cannot generate video because audio file is missing: %s", audio.path)
            raise AudioFileNotFoundError(audio.path)

        background_path = self.image_service.ensure_default_background()
        output_path = f"storage/videos/video_{audio.id}.mp4"
        logger.info("Generating video for audio_id=%s", audio.id)

        try:
            self.ffmpeg_service.create_video_from_image_and_audio(
                image_path=background_path,
                audio_path=audio.path,
                output_path=output_path,
            )
            video = Video(audio_id=audio.id, path=output_path, status=VideoStatus.GENERATED)
            self.db.add(video)
            self.db.commit()
            self.db.refresh(video)
            logger.info("Generated video id=%s audio_id=%s path=%s", video.id, audio.id, video.path)
            return video
        except Exception:
            self.db.rollback()
            logger.exception("Video generation failed for audio_id=%s", audio.id)
            raise
