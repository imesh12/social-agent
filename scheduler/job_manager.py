import logging
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.manager_agent import ManagerAgent
from database.models import (
    Audio,
    PublishJob,
    ScheduledJob,
    ScheduledJobStatus,
    SEO,
    Script,
    Subtitle,
    Thumbnail,
    Video,
)
from services.metadata_service import GenerationMetadataService

logger = logging.getLogger(__name__)


class JobManager:
    def __init__(
        self,
        db: Session,
        manager_factory: Callable[[Session], ManagerAgent],
        daily_video_count: int = 3,
    ) -> None:
        self.db = db
        self.manager_factory = manager_factory
        self.daily_video_count = daily_video_count
        self.metadata_service = GenerationMetadataService()

    async def run_full_pipeline(self) -> dict[str, int | str]:
        job = self._start_job("run_full_pipeline")
        try:
            manager = self.manager_factory(self.db)
            script = manager.generate_script()
            audio = await manager.generate_audio(script_id=script.id)
            video = manager.generate_video(audio_id=audio.id)
            subtitle = manager.generate_subtitles(video_id=video.id)
            seo = manager.generate_seo(video_id=video.id)
            thumbnail = manager.generate_thumbnail(video_id=video.id)
            self.metadata_service.save_for_video(self.db, video_id=video.id)
            self._complete_job(job)
            return {
                "status": "completed",
                "script_id": script.id,
                "audio_id": audio.id,
                "video_id": video.id,
                "subtitle_id": subtitle.id,
                "seo_id": seo.id,
                "thumbnail_id": thumbnail.id,
            }
        except Exception:
            self._fail_job(job)
            logger.exception("Full pipeline job failed")
            raise

    async def run_daily_jobs(self) -> dict[str, int | str]:
        job = self._start_job("run_daily_jobs")
        try:
            scripts_created = self.generate_scripts()
            audio_created = await self.generate_audio()
            videos_created = self.generate_videos()
            subtitles_created = self.generate_subtitles()
            seo_created = self.generate_seo()
            thumbnails_created = self.generate_thumbnails()
            self._complete_job(job)
            return {
                "status": "completed",
                "scripts_created": scripts_created,
                "audio_created": audio_created,
                "videos_created": videos_created,
                "subtitles_created": subtitles_created,
                "seo_created": seo_created,
                "thumbnails_created": thumbnails_created,
            }
        except Exception:
            self._fail_job(job)
            logger.exception("Daily jobs run failed")
            raise

    def generate_scripts(self) -> int:
        job = self._start_job("generate_scripts")
        try:
            manager = self.manager_factory(self.db)
            for _ in range(self.daily_video_count):
                manager.generate_script()
            self._complete_job(job)
            logger.info("Generated %s scripts", self.daily_video_count)
            return self.daily_video_count
        except Exception:
            self._fail_job(job)
            logger.exception("Generate scripts job failed")
            raise

    async def generate_audio(self) -> int:
        job = self._start_job("generate_audio")
        try:
            manager = self.manager_factory(self.db)
            scripts = self._scripts_without_audio()
            created = 0
            for script in scripts:
                try:
                    await manager.generate_audio(script_id=script.id)
                    created += 1
                except Exception:
                    logger.exception("Skipping audio generation for script_id=%s", script.id)
                    continue
            self._complete_job(job)
            logger.info("Generated %s audio files", created)
            return created
        except Exception:
            self._fail_job(job)
            logger.exception("Generate audio job failed")
            raise

    def generate_videos(self) -> int:
        job = self._start_job("generate_videos")
        try:
            manager = self.manager_factory(self.db)
            audios = self._audios_without_video()
            created = 0
            for audio in audios:
                try:
                    manager.generate_video(audio_id=audio.id)
                    created += 1
                except Exception:
                    logger.exception("Skipping video generation for audio_id=%s", audio.id)
                    continue
            self._complete_job(job)
            logger.info("Generated %s videos", created)
            return created
        except Exception:
            self._fail_job(job)
            logger.exception("Generate videos job failed")
            raise

    def generate_subtitles(self) -> int:
        job = self._start_job("generate_subtitles")
        try:
            manager = self.manager_factory(self.db)
            videos = self._videos_without_subtitles()
            for video in videos:
                manager.generate_subtitles(video_id=video.id)
            self._complete_job(job)
            logger.info("Generated %s subtitle files", len(videos))
            return len(videos)
        except Exception:
            self._fail_job(job)
            logger.exception("Generate subtitles job failed")
            raise

    def generate_seo(self) -> int:
        job = self._start_job("generate_seo")
        try:
            manager = self.manager_factory(self.db)
            videos = self._videos_without_seo()
            for video in videos:
                manager.generate_seo(video_id=video.id)
            self._complete_job(job)
            logger.info("Generated %s SEO records", len(videos))
            return len(videos)
        except Exception:
            self._fail_job(job)
            logger.exception("Generate SEO job failed")
            raise

    def generate_thumbnails(self) -> int:
        job = self._start_job("generate_thumbnails")
        try:
            manager = self.manager_factory(self.db)
            videos = self._videos_without_thumbnails()
            for video in videos:
                manager.generate_thumbnail(video_id=video.id)
                self.metadata_service.save_for_video(self.db, video_id=video.id)
            self._complete_job(job)
            logger.info("Generated %s thumbnails", len(videos))
            return len(videos)
        except Exception:
            self._fail_job(job)
            logger.exception("Generate thumbnails job failed")
            raise

    def publish_video(self, slot: int) -> PublishJob:
        job = self._start_job(f"publish_video_{slot}")
        try:
            videos = self._unpublished_videos()
            if len(videos) < slot:
                raise ValueError(f"No unpublished video is available for publish slot {slot}")
            manager = self.manager_factory(self.db)
            publish_job: PublishJob | None = None
            for video in videos[slot - 1:]:
                try:
                    publish_job = manager.publish_youtube(video_id=video.id)
                    break
                except Exception:
                    logger.exception("Skipping publish for video_id=%s slot=%s", video.id, slot)
                    continue
            if publish_job is None:
                raise RuntimeError(f"No video could be published for slot {slot}")
            self._complete_job(job)
            self.metadata_service.save_for_video(
                self.db,
                video_id=publish_job.video_id,
                youtube_id=publish_job.youtube_video_id,
            )
            logger.info("Published video slot=%s video_id=%s", slot, publish_job.video_id)
            return publish_job
        except Exception:
            self._fail_job(job)
            logger.exception("Publish video job failed for slot=%s", slot)
            raise

    def scheduler_status(self) -> dict[str, int | str | None]:
        latest = self.db.scalars(
            select(ScheduledJob).order_by(ScheduledJob.started_at.desc())
        ).first()
        return {
            "last_job_type": latest.job_type if latest else None,
            "last_job_status": latest.status.value if latest else None,
            "scheduled_job_count": self.db.query(ScheduledJob).count(),
        }

    def _scripts_without_audio(self) -> list[Script]:
        return list(
            self.db.scalars(
                select(Script)
                .outerjoin(Audio)
                .where(Audio.id.is_(None))
                .order_by(Script.created_at.asc())
            )
        )

    def _audios_without_video(self) -> list[Audio]:
        return list(
            self.db.scalars(
                select(Audio)
                .outerjoin(Video)
                .where(Video.id.is_(None))
                .order_by(Audio.created_at.asc())
            )
        )

    def _videos_without_subtitles(self) -> list[Video]:
        return list(
            self.db.scalars(
                select(Video)
                .outerjoin(Subtitle)
                .where(Subtitle.id.is_(None))
                .order_by(Video.created_at.asc())
            )
        )

    def _videos_without_seo(self) -> list[Video]:
        return list(
            self.db.scalars(
                select(Video)
                .join(Subtitle)
                .outerjoin(SEO)
                .where(SEO.id.is_(None))
                .order_by(Video.created_at.asc())
            )
        )

    def _videos_without_thumbnails(self) -> list[Video]:
        return list(
            self.db.scalars(
                select(Video)
                .join(SEO)
                .outerjoin(Thumbnail)
                .where(Thumbnail.id.is_(None))
                .order_by(Video.created_at.asc())
            )
        )

    def _unpublished_videos(self) -> list[Video]:
        return list(
            self.db.scalars(
                select(Video)
                .join(SEO)
                .join(Thumbnail)
                .outerjoin(PublishJob)
                .where(PublishJob.id.is_(None))
                .order_by(Video.created_at.asc())
            )
        )

    def _start_job(self, job_type: str) -> ScheduledJob:
        job = ScheduledJob(job_type=job_type, status=ScheduledJobStatus.RUNNING)
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def _complete_job(self, job: ScheduledJob) -> None:
        job.status = ScheduledJobStatus.COMPLETED
        job.completed_at = datetime.now(timezone.utc)
        self.db.commit()

    def _fail_job(self, job: ScheduledJob) -> None:
        job.status = ScheduledJobStatus.FAILED
        job.completed_at = datetime.now(timezone.utc)
        self.db.commit()
