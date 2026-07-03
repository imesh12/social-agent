import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.manager_agent import ManagerAgent
from database.models import (
    Audio,
    PipelineStage,
    PipelineTask,
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
from services.pipeline_state_service import PipelineStateMachine
from services.pipeline_report_service import PipelineReportService

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
        self.pipeline_report_service = PipelineReportService()
        self.pipeline_state = PipelineStateMachine(db)

    async def run_full_pipeline(self) -> dict[str, int | str]:
        job = self._start_job("run_full_pipeline")
        report = self.pipeline_report_service.start_report()
        try:
            manager = self.manager_factory(self.db)
            script = self._run_report_stage(report, "script", manager.generate_script)
            audio = await self._run_report_stage_async(
                report,
                "audio",
                manager.generate_audio,
                script_id=script.id,
            ) if script is not None else self._skip_report_stage(report, "audio", "script generation failed")
            video = self._run_report_stage(
                report,
                "video",
                manager.generate_video,
                audio_id=audio.id,
            ) if audio is not None else self._skip_report_stage(report, "video", "audio generation failed")
            subtitle = self._run_report_stage(
                report,
                "subtitles",
                manager.generate_subtitles,
                video_id=video.id,
            ) if video is not None else self._skip_report_stage(report, "subtitles", "video generation failed")
            seo = self._run_report_stage(
                report,
                "seo",
                manager.generate_seo,
                video_id=video.id,
            ) if video is not None else self._skip_report_stage(report, "seo", "video generation failed")
            thumbnail = self._run_report_stage(
                report,
                "thumbnail",
                manager.generate_thumbnail,
                video_id=video.id,
            ) if video is not None else self._skip_report_stage(report, "thumbnail", "video generation failed")
            publish_job = self._run_report_stage(
                report,
                "publish",
                manager.publish_youtube,
                video_id=video.id,
            ) if video is not None and seo is not None and thumbnail is not None else self._skip_report_stage(
                report,
                "publish",
                "video, seo, or thumbnail unavailable",
            )
            metadata_path = None
            if video is not None:
                metadata_path = self._run_report_stage(
                    report,
                    "metadata",
                    self.metadata_service.save_for_video,
                    self.db,
                    video_id=video.id,
                    youtube_id=publish_job.youtube_video_id if publish_job is not None else None,
                )
                metadata = self._load_latest_metadata()
                report["scores"] = self.pipeline_report_service.collect_scores(metadata)
                report["upload_status"] = metadata.get("youtube_upload", {})
            else:
                self._skip_report_stage(report, "metadata", "video generation failed")

            if publish_job is not None and getattr(publish_job.status, "value", "") == "failed":
                report["errors"].append({"stage": "publish", "error": "YouTube upload failed"})
                self.pipeline_report_service.save_report(report)

            self._complete_job(job)
            report_path = self.pipeline_report_service.finalize(report)
            return {
                "status": report["status"],
                "script_id": script.id if script is not None else 0,
                "audio_id": audio.id if audio is not None else 0,
                "video_id": video.id if video is not None else 0,
                "subtitle_id": subtitle.id if subtitle is not None else 0,
                "seo_id": seo.id if seo is not None else 0,
                "thumbnail_id": thumbnail.id if thumbnail is not None else 0,
                "publish_job_id": publish_job.id if publish_job is not None else 0,
                "report_path": str(report_path).replace("\\", "/"),
                "metadata_path": str(metadata_path).replace("\\", "/") if metadata_path else "",
            }
        except Exception:
            self._fail_job(job)
            logger.exception("Full pipeline job failed")
            report["errors"].append({"stage": "pipeline", "error": "Full pipeline job failed"})
            report_path = self.pipeline_report_service.finalize(report)
            return {
                "status": "failed",
                "script_id": 0,
                "audio_id": 0,
                "video_id": 0,
                "subtitle_id": 0,
                "seo_id": 0,
                "thumbnail_id": 0,
                "publish_job_id": 0,
                "report_path": str(report_path).replace("\\", "/"),
                "metadata_path": "",
            }

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
            self._prepare_pipeline_tasks()
            manager = self.manager_factory(self.db)
            tasks = self.pipeline_state.tasks_at_stage(PipelineStage.SCRIPT_READY)
            created = 0
            for task in tasks:
                script_id = self._task_int(task, "script_id")
                if script_id is None:
                    logger.warning("Skipping audio generation for task_uuid=%s missing script_id", task.task_uuid)
                    continue
                try:
                    await manager.generate_audio(script_id=script_id)
                    created += 1
                except Exception:
                    logger.exception("Skipping audio generation for task_uuid=%s script_id=%s", task.task_uuid, script_id)
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
            self._prepare_pipeline_tasks()
            manager = self.manager_factory(self.db)
            tasks = self.pipeline_state.tasks_at_stage(PipelineStage.AUDIO_READY)
            created = 0
            for task in tasks:
                audio_id = self._task_int(task, "audio_id")
                if audio_id is None:
                    logger.warning("Skipping video generation for task_uuid=%s missing audio_id", task.task_uuid)
                    continue
                try:
                    manager.generate_video(audio_id=audio_id)
                    created += 1
                except Exception:
                    logger.exception("Skipping video generation for task_uuid=%s audio_id=%s", task.task_uuid, audio_id)
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
            self._prepare_pipeline_tasks()
            manager = self.manager_factory(self.db)
            tasks = self.pipeline_state.tasks_at_stage(PipelineStage.VIDEO_READY)
            created = 0
            for task in tasks:
                video_id = self._task_int(task, "video_id")
                if video_id is None:
                    logger.warning("Skipping subtitle generation for task_uuid=%s missing video_id", task.task_uuid)
                    continue
                manager.generate_subtitles(video_id=video_id)
                created += 1
            self._complete_job(job)
            logger.info("Generated %s subtitle files", created)
            return created
        except Exception:
            self._fail_job(job)
            logger.exception("Generate subtitles job failed")
            raise

    def generate_seo(self) -> int:
        job = self._start_job("generate_seo")
        try:
            self._prepare_pipeline_tasks()
            manager = self.manager_factory(self.db)
            tasks = self.pipeline_state.tasks_at_stage(PipelineStage.SUBTITLE_READY)
            created = 0
            for task in tasks:
                video_id = self._task_int(task, "video_id")
                if video_id is None:
                    logger.warning("Skipping SEO generation for task_uuid=%s missing video_id", task.task_uuid)
                    continue
                manager.generate_seo(video_id=video_id)
                created += 1
            self._complete_job(job)
            logger.info("Generated %s SEO records", created)
            return created
        except Exception:
            self._fail_job(job)
            logger.exception("Generate SEO job failed")
            raise

    def generate_thumbnails(self) -> int:
        job = self._start_job("generate_thumbnails")
        try:
            self._prepare_pipeline_tasks()
            manager = self.manager_factory(self.db)
            tasks = self.pipeline_state.tasks_at_stage(PipelineStage.SEO_READY)
            created = 0
            for task in tasks:
                video_id = self._task_int(task, "video_id")
                if video_id is None:
                    logger.warning("Skipping thumbnail generation for task_uuid=%s missing video_id", task.task_uuid)
                    continue
                manager.generate_thumbnail(video_id=video_id)
                self.metadata_service.save_for_video(self.db, video_id=video_id)
                created += 1
            self._complete_job(job)
            logger.info("Generated %s thumbnails", created)
            return created
        except Exception:
            self._fail_job(job)
            logger.exception("Generate thumbnails job failed")
            raise

    def publish_video(self, slot: int) -> PublishJob:
        job = self._start_job(f"publish_video_{slot}")
        try:
            self._prepare_pipeline_tasks()
            tasks = self.pipeline_state.tasks_at_stage(PipelineStage.READY_FOR_UPLOAD)
            if len(tasks) < slot:
                raise ValueError(f"No unpublished video is available for publish slot {slot}")
            manager = self.manager_factory(self.db)
            publish_job: PublishJob | None = None
            for task in tasks[slot - 1:]:
                video_id = self._task_int(task, "video_id")
                if video_id is None:
                    logger.warning("Skipping publish for task_uuid=%s missing video_id slot=%s", task.task_uuid, slot)
                    continue
                try:
                    publish_job = manager.publish_youtube(video_id=video_id)
                    break
                except Exception:
                    logger.exception("Skipping publish for task_uuid=%s video_id=%s slot=%s", task.task_uuid, video_id, slot)
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

    def _run_report_stage(self, report: dict[str, Any], name: str, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        stage = self.pipeline_report_service.start_stage(report, name)
        try:
            result = func(*args, **kwargs)
            self.pipeline_report_service.complete_stage(report, stage, self._stage_details(result))
            return result
        except Exception as exc:
            logger.exception("Full pipeline stage failed name=%s", name)
            self.pipeline_report_service.fail_stage(report, stage, str(exc))
            return None

    async def _run_report_stage_async(
        self,
        report: dict[str, Any],
        name: str,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        stage = self.pipeline_report_service.start_stage(report, name)
        try:
            result = await func(*args, **kwargs)
            self.pipeline_report_service.complete_stage(report, stage, self._stage_details(result))
            return result
        except Exception as exc:
            logger.exception("Full pipeline stage failed name=%s", name)
            self.pipeline_report_service.fail_stage(report, stage, str(exc))
            return None

    def _skip_report_stage(self, report: dict[str, Any], name: str, reason: str) -> None:
        self.pipeline_report_service.skip_stage(report, name, reason)
        return None

    def _stage_details(self, result: Any) -> dict[str, Any]:
        details: dict[str, Any] = {}
        for attr in ("id", "path", "title", "youtube_video_id", "youtube_url", "status"):
            if hasattr(result, attr):
                value = getattr(result, attr)
                details[attr] = getattr(value, "value", value)
        return details

    def _load_latest_metadata(self) -> dict[str, Any]:
        import json

        path = self.metadata_service.output_dir / "latest.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to load latest metadata for pipeline report")
            return {}

    def _task_int(self, task: PipelineTask, key: str) -> int | None:
        value = self.pipeline_state.metadata(task).get(key)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            logger.warning("Invalid pipeline task metadata task_uuid=%s key=%s value=%s", task.task_uuid, key, value)
            return None

    def _prepare_pipeline_tasks(self) -> None:
        """Reconcile legacy rows and due retries before scheduler stage selection."""
        self._ensure_legacy_tasks()
        self.pipeline_state.activate_due_retries()

    def _ensure_legacy_tasks(self) -> None:
        """Create PipelineTask records for legacy rows so scheduler uses state only after adoption."""
        for script in self._scripts_without_task():
            self.pipeline_state.create_task(
                topic_id=script.topic_id,
                current_stage=PipelineStage.SCRIPT_READY,
                metadata={"script_id": script.id, "topic_id": script.topic_id},
            )
        for audio in self._audios_without_task():
            self.pipeline_state.create_task(
                topic_id=audio.script.topic_id,
                current_stage=PipelineStage.AUDIO_READY,
                metadata={"script_id": audio.script_id, "audio_id": audio.id, "topic_id": audio.script.topic_id},
            )
        for video in self._videos_without_task():
            self.pipeline_state.create_task(
                topic_id=video.audio.script.topic_id,
                video_id=video.id,
                current_stage=PipelineStage.VIDEO_READY,
                metadata={
                    "script_id": video.audio.script_id,
                    "audio_id": video.audio_id,
                    "video_id": video.id,
                    "topic_id": video.audio.script.topic_id,
                },
            )

    def _scripts_without_task(self) -> list[Script]:
        return [
            script
            for script in self.db.scalars(select(Script).order_by(Script.created_at.asc()))
            if self.pipeline_state.task_for_topic(script.topic_id) is None
        ]

    def _audios_without_task(self) -> list[Audio]:
        return [
            audio
            for audio in self.db.scalars(select(Audio).order_by(Audio.created_at.asc()))
            if self.pipeline_state.task_for_topic(audio.script.topic_id) is None
        ]

    def _videos_without_task(self) -> list[Video]:
        return [
            video
            for video in self.db.scalars(select(Video).order_by(Video.created_at.asc()))
            if self.pipeline_state.task_for_video(video.id) is None
            and self.pipeline_state.task_for_topic(video.audio.script.topic_id) is None
        ]
