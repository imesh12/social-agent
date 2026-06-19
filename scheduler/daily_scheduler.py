import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from agents.factory import build_manager_agent
from database.database import SessionLocal
from scheduler.job_manager import JobManager
from services.cleanup_service import CleanupService

logger = logging.getLogger(__name__)


def create_daily_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Tokyo")
    scheduler.add_job(_cleanup_job, "cron", hour=2, minute=0, id="cleanup_storage", replace_existing=True)
    scheduler.add_job(_generate_scripts_job, "cron", hour=6, minute=0, id="generate_scripts", replace_existing=True)
    scheduler.add_job(_generate_audio_job, "cron", hour=6, minute=10, id="generate_audio", replace_existing=True)
    scheduler.add_job(_generate_videos_job, "cron", hour=6, minute=20, id="generate_videos", replace_existing=True)
    scheduler.add_job(_generate_subtitles_job, "cron", hour=6, minute=25, id="generate_subtitles", replace_existing=True)
    scheduler.add_job(_generate_seo_job, "cron", hour=6, minute=30, id="generate_seo", replace_existing=True)
    scheduler.add_job(_generate_thumbnails_job, "cron", hour=6, minute=35, id="generate_thumbnails", replace_existing=True)
    scheduler.add_job(_publish_video_job, "cron", hour=12, minute=0, args=[1], id="publish_video_1", replace_existing=True)
    scheduler.add_job(_publish_video_job, "cron", hour=18, minute=0, args=[2], id="publish_video_2", replace_existing=True)
    scheduler.add_job(_publish_video_job, "cron", hour=21, minute=0, args=[3], id="publish_video_3", replace_existing=True)
    return scheduler


async def _cleanup_job() -> None:
    try:
        CleanupService().cleanup_old_files()
    except Exception:
        logger.exception("Scheduled cleanup failed")


def scheduler_snapshot(scheduler: AsyncIOScheduler) -> dict[str, object]:
    return {
        "running": scheduler.running,
        "jobs": [
            {
                "id": job.id,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            }
            for job in scheduler.get_jobs()
        ],
    }


def _job_manager() -> JobManager:
    db = SessionLocal()
    return JobManager(db=db, manager_factory=build_manager_agent)


async def _generate_scripts_job() -> None:
    manager = _job_manager()
    try:
        manager.generate_scripts()
    finally:
        manager.db.close()


async def _generate_audio_job() -> None:
    manager = _job_manager()
    try:
        await manager.generate_audio()
    finally:
        manager.db.close()


async def _generate_videos_job() -> None:
    manager = _job_manager()
    try:
        manager.generate_videos()
    finally:
        manager.db.close()


async def _generate_subtitles_job() -> None:
    manager = _job_manager()
    try:
        manager.generate_subtitles()
    finally:
        manager.db.close()


async def _generate_seo_job() -> None:
    manager = _job_manager()
    try:
        manager.generate_seo()
    finally:
        manager.db.close()


async def _generate_thumbnails_job() -> None:
    manager = _job_manager()
    try:
        manager.generate_thumbnails()
    finally:
        manager.db.close()


async def _publish_video_job(slot: int) -> None:
    manager = _job_manager()
    try:
        manager.publish_video(slot=slot)
    finally:
        manager.db.close()
