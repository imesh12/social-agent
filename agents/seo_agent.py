import json
import logging

from sqlalchemy.orm import Session

from database.models import SEO, Video
from services.llm.base_llm_service import BaseLLMService
from services.metadata_service import GenerationMetadataService
from services.seo_intelligence_service import SEOIntelligenceService

logger = logging.getLogger(__name__)


class SEOVideoNotFoundError(Exception):
    def __init__(self, video_id: int) -> None:
        super().__init__(f"Video {video_id} was not found")
        self.video_id = video_id


class SEOAgent:
    def __init__(
        self,
        db: Session,
        llm_service: BaseLLMService,
        seo_intelligence_service: SEOIntelligenceService | None = None,
        metadata_service: GenerationMetadataService | None = None,
    ) -> None:
        self.db = db
        self.llm_service = llm_service
        self.seo_intelligence_service = seo_intelligence_service
        self.metadata_service = metadata_service or GenerationMetadataService()

    def generate_seo(self, video_id: int) -> SEO:
        video = self.db.get(Video, video_id)
        if video is None:
            logger.warning("Cannot generate SEO because video_id=%s was not found", video_id)
            raise SEOVideoNotFoundError(video_id)

        script_text = video.audio.script.content
        logger.info("Generating SEO metadata for video_id=%s", video.id)

        try:
            metadata = self.llm_service.generate_seo(script_text=script_text)
            intelligence = None
            if self.seo_intelligence_service is not None:
                selection = self.seo_intelligence_service.optimize_seo(
                    script_text=script_text,
                    initial_seo=metadata,
                )
                metadata = selection.seo
                intelligence = selection.intelligence
            seo = SEO(
                video_id=video.id,
                title=metadata.title,
                description=metadata.description,
                tags=json.dumps(metadata.tags),
                hashtags=metadata.hashtags,
            )
            self.db.add(seo)
            self.db.commit()
            self.db.refresh(seo)
            self.metadata_service.save_seo_intelligence(video_id=video.id, result=intelligence)
            logger.info("Generated SEO id=%s video_id=%s", seo.id, video.id)
            return seo
        except Exception:
            self.db.rollback()
            logger.exception("SEO generation failed for video_id=%s", video.id)
            raise
