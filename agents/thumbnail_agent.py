import logging
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from database.models import Thumbnail, Video
from services.metadata_service import GenerationMetadataService
from services.thumbnail_intelligence_service import ThumbnailIntelligenceResult, ThumbnailIntelligenceService
from services.thumbnail_service import ThumbnailService

logger = logging.getLogger(__name__)


class ThumbnailVideoNotFoundError(Exception):
    def __init__(self, video_id: int) -> None:
        super().__init__(f"Video {video_id} was not found")
        self.video_id = video_id


class ThumbnailAgent:
    def __init__(
        self,
        db: Session,
        thumbnail_service: ThumbnailService,
        thumbnail_intelligence_service: ThumbnailIntelligenceService | None = None,
        metadata_service: GenerationMetadataService | None = None,
    ) -> None:
        self.db = db
        self.thumbnail_service = thumbnail_service
        self.thumbnail_intelligence_service = thumbnail_intelligence_service
        self.metadata_service = metadata_service or GenerationMetadataService()

    def generate_thumbnail(self, video_id: int) -> Thumbnail:
        video = self.db.get(Video, video_id)
        if video is None:
            logger.warning("Cannot generate thumbnail because video_id=%s was not found", video_id)
            raise ThumbnailVideoNotFoundError(video_id)

        output_path = f"storage/thumbnails/thumb_{video.id}.jpg"
        logger.info("Generating thumbnail for video_id=%s", video.id)

        try:
            intelligence = self._generate_best_thumbnail(output_path=output_path, video_id=video.id)
            thumbnail = Thumbnail(video_id=video.id, path=output_path)
            self.db.add(thumbnail)
            self.db.commit()
            self.db.refresh(thumbnail)
            self.metadata_service.save_thumbnail_intelligence(video_id=video.id, result=intelligence)
            logger.info("Generated thumbnail id=%s video_id=%s path=%s", thumbnail.id, video.id, thumbnail.path)
            return thumbnail
        except Exception:
            self.db.rollback()
            logger.exception("Thumbnail generation failed for video_id=%s", video.id)
            raise

    def _generate_best_thumbnail(self, output_path: str, video_id: int) -> ThumbnailIntelligenceResult | None:
        """Generate thumbnail attempts and keep the highest scoring one."""
        if self.thumbnail_intelligence_service is None:
            self.thumbnail_service.generate_thumbnail(output_path=output_path)
            return None

        best_result: ThumbnailIntelligenceResult | None = None
        best_attempt_path = output_path
        max_attempts = self.thumbnail_intelligence_service.max_regeneration_attempts + 1
        for attempt in range(max_attempts):
            attempt_path = self._attempt_path(output_path=output_path, attempt=attempt)
            self.thumbnail_service.generate_thumbnail(output_path=attempt_path)
            result = self.thumbnail_intelligence_service.analyze_thumbnail(
                thumbnail_path=attempt_path,
                attempt=attempt,
            )
            if best_result is None or result.overall_score > best_result.overall_score:
                best_result = result
                best_attempt_path = attempt_path
            if result.overall_score >= self.thumbnail_intelligence_service.acceptance_threshold:
                break

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        if best_attempt_path != output_path:
            shutil.copyfile(best_attempt_path, output_path)
        elif not Path(output_path).exists():
            self.thumbnail_service.generate_thumbnail(output_path=output_path)

        if best_result is not None:
            best_result.selected_thumbnail_path = output_path
            best_result.accepted = best_result.overall_score >= self.thumbnail_intelligence_service.acceptance_threshold
        logger.info(
            "Thumbnail intelligence selected video_id=%s score=%s attempt=%s accepted=%s",
            video_id,
            best_result.overall_score if best_result else None,
            best_result.regeneration_attempt if best_result else None,
            best_result.accepted if best_result else None,
        )
        return best_result

    def _attempt_path(self, output_path: str, attempt: int) -> str:
        path = Path(output_path)
        return str(path.with_name(f"{path.stem}_attempt_{attempt}{path.suffix}"))
