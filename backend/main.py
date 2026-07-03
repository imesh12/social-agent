import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from agents.factory import build_manager_agent
from agents.manager_agent import ManagerAgent
from agents.publisher_agent import (
    PublishVideoFileNotFoundError,
    PublishVideoNotFoundError,
    PublisherAgent,
)
from agents.research_agent import ResearchAgent
from agents.seo_agent import SEOVideoNotFoundError
from agents.script_agent import ScriptAgent
from agents.subtitle_agent import SubtitleAgent, VideoNotFoundError
from agents.thumbnail_agent import ThumbnailVideoNotFoundError
from agents.trend_agent import TrendAgent
from agents.video_agent import AudioFileNotFoundError, AudioNotFoundError, VideoAgent
from agents.voice_agent import ScriptNotFoundError, VoiceAgent
from backend.config import Settings, get_settings
from backend.routes.auth import router as auth_router
from backend.routes.system_health import router as system_health_router
from backend.routes.youtube_oauth import router as youtube_oauth_router
from backend.session import SignedCookieSessionMiddleware
from database.database import Base, SessionLocal, engine, get_db
from schemas.publish_schema import YouTubePublishRequest, YouTubePublishResponse
from schemas.seo_schema import SEOGenerateRequest, SEOGenerateResponse
from schemas.script_schema import ScriptGenerateResponse
from schemas.subtitle_schema import SubtitleGenerateRequest, SubtitleGenerateResponse
from schemas.thumbnail_schema import ThumbnailGenerateRequest, ThumbnailGenerateResponse
from schemas.topic_schema import TopicGenerateResponse
from schemas.video_schema import VideoGenerateRequest, VideoGenerateResponse
from schemas.voice_schema import AudioGenerateRequest, AudioGenerateResponse
from platforms.youtube import YouTubePublisherAdapter
from services.image_service import ImageService
from services.pipeline_state_service import PipelineStateMachine
from services.publisher import PublisherService
from scheduler.daily_scheduler import create_daily_scheduler, scheduler_snapshot
from scheduler.job_manager import JobManager
import json


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)
    settings.storage_dir.mkdir(exist_ok=True)
    for child in (
        "topics",
        "scripts",
        "audio",
        "backgrounds",
        "videos",
        "subtitles",
        "thumbnails",
        "uploads",
        "generated",
        "temp",
        "music",
        "logs",
    ):
        (settings.storage_dir / child).mkdir(parents=True, exist_ok=True)
    ImageService().ensure_default_background()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        PipelineStateMachine(db).recover_stale_running()
    finally:
        db.close()
    app.state.publisher_service = PublisherService()
    app.state.publisher_service.register_adapter(YouTubePublisherAdapter(settings=settings))
    app.state.scheduler = create_daily_scheduler()
    app.state.scheduler.start()
    logging.getLogger(__name__).info("Application startup complete")
    yield
    app.state.scheduler.shutdown(wait=False)


app = FastAPI(title="social-media-ai", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    SignedCookieSessionMiddleware,
    secret_key=get_settings().session_secret_key,
    same_site="lax",
    https_only=False,
)
app.include_router(auth_router)
app.include_router(youtube_oauth_router)
app.include_router(system_health_router)
for static_dir in ("storage/logs", "storage/generated", "storage/videos", "storage/thumbnails"):
    Path(static_dir).mkdir(parents=True, exist_ok=True)
app.mount("/ui", StaticFiles(directory="frontend", html=True), name="ui")
app.mount("/storage/logs", StaticFiles(directory="storage/logs"), name="storage_logs")
app.mount("/storage/generated", StaticFiles(directory="storage/generated"), name="storage_generated")
app.mount("/storage/videos", StaticFiles(directory="storage/videos"), name="storage_videos")
app.mount("/storage/thumbnails", StaticFiles(directory="storage/thumbnails"), name="storage_thumbnails")


def get_manager_agent(db: Session = Depends(get_db)) -> ManagerAgent:
    return build_manager_agent(db)


def get_job_manager(db: Session = Depends(get_db)) -> JobManager:
    return JobManager(db=db, manager_factory=build_manager_agent)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/generate-topic", response_model=TopicGenerateResponse)
def generate_topic(manager_agent: ManagerAgent = Depends(get_manager_agent)) -> TopicGenerateResponse:
    try:
        topic = manager_agent.generate_topic()
        return TopicGenerateResponse(topic=topic.title, score=topic.score)
    except Exception as exc:
        logging.getLogger(__name__).exception("Topic generation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Topic generation failed",
        ) from exc


@app.post("/generate-script", response_model=ScriptGenerateResponse)
def generate_script(manager_agent: ManagerAgent = Depends(get_manager_agent)) -> ScriptGenerateResponse:
    try:
        script = manager_agent.generate_script()
        return ScriptGenerateResponse(script=script.content)
    except Exception as exc:
        logging.getLogger(__name__).exception("Script generation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Script generation failed",
        ) from exc


@app.post("/generate-audio", response_model=AudioGenerateResponse)
async def generate_audio(
    request: AudioGenerateRequest,
    manager_agent: ManagerAgent = Depends(get_manager_agent),
) -> AudioGenerateResponse:
    try:
        audio = await manager_agent.generate_audio(script_id=request.script_id, voice=request.voice)
        return AudioGenerateResponse(audio_path=audio.path)
    except ScriptNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Script {exc.script_id} was not found",
        ) from exc
    except Exception as exc:
        logging.getLogger(__name__).exception("Audio generation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Audio generation failed",
        ) from exc


@app.post("/generate-video", response_model=VideoGenerateResponse)
def generate_video(
    request: VideoGenerateRequest,
    manager_agent: ManagerAgent = Depends(get_manager_agent),
) -> VideoGenerateResponse:
    try:
        video = manager_agent.generate_video(audio_id=request.audio_id)
        return VideoGenerateResponse(video_path=video.path)
    except AudioNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audio {exc.audio_id} was not found",
        ) from exc
    except AudioFileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audio file {exc.audio_path} was not found",
        ) from exc
    except Exception as exc:
        logging.getLogger(__name__).exception("Video generation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Video generation failed",
        ) from exc


@app.post("/generate-subtitles", response_model=SubtitleGenerateResponse)
def generate_subtitles(
    request: SubtitleGenerateRequest,
    manager_agent: ManagerAgent = Depends(get_manager_agent),
) -> SubtitleGenerateResponse:
    try:
        subtitle = manager_agent.generate_subtitles(video_id=request.video_id)
        return SubtitleGenerateResponse(subtitle_path=subtitle.path)
    except VideoNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video {exc.video_id} was not found",
        ) from exc
    except Exception as exc:
        logging.getLogger(__name__).exception("Subtitle generation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Subtitle generation failed",
        ) from exc


@app.post("/generate-seo", response_model=SEOGenerateResponse)
def generate_seo(
    request: SEOGenerateRequest,
    manager_agent: ManagerAgent = Depends(get_manager_agent),
) -> SEOGenerateResponse:
    try:
        seo = manager_agent.generate_seo(video_id=request.video_id)
        return SEOGenerateResponse(
            title=seo.title,
            description=seo.description,
            tags=json.loads(seo.tags),
            hashtags=seo.hashtags,
        )
    except SEOVideoNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video {exc.video_id} was not found",
        ) from exc
    except Exception as exc:
        logging.getLogger(__name__).exception("SEO generation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SEO generation failed",
        ) from exc


@app.post("/generate-thumbnail", response_model=ThumbnailGenerateResponse)
def generate_thumbnail(
    request: ThumbnailGenerateRequest,
    manager_agent: ManagerAgent = Depends(get_manager_agent),
) -> ThumbnailGenerateResponse:
    try:
        thumbnail = manager_agent.generate_thumbnail(video_id=request.video_id)
        return ThumbnailGenerateResponse(thumbnail_path=thumbnail.path)
    except ThumbnailVideoNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video {exc.video_id} was not found",
        ) from exc
    except Exception as exc:
        logging.getLogger(__name__).exception("Thumbnail generation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Thumbnail generation failed",
        ) from exc


@app.post("/publish-youtube", response_model=YouTubePublishResponse)
def publish_youtube(
    request: YouTubePublishRequest,
    manager_agent: ManagerAgent = Depends(get_manager_agent),
) -> YouTubePublishResponse:
    try:
        publish_job = manager_agent.publish_youtube(video_id=request.video_id)
        return YouTubePublishResponse(
            status=publish_job.status.value,
            youtube_url=publish_job.youtube_url or "",
        )
    except PublishVideoNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video {exc.video_id} was not found",
        ) from exc
    except PublishVideoFileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video file {exc.video_path} was not found",
        ) from exc
    except Exception as exc:
        logging.getLogger(__name__).exception("YouTube publish failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="YouTube publish failed",
        ) from exc


@app.post("/run-full-pipeline")
async def run_full_pipeline(job_manager: JobManager = Depends(get_job_manager)) -> dict[str, int | str]:
    try:
        return await job_manager.run_full_pipeline()
    except Exception as exc:
        logging.getLogger(__name__).exception("Full pipeline failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Full pipeline failed",
        ) from exc


@app.post("/run-daily-jobs")
async def run_daily_jobs(job_manager: JobManager = Depends(get_job_manager)) -> dict[str, int | str]:
    try:
        return await job_manager.run_daily_jobs()
    except Exception as exc:
        logging.getLogger(__name__).exception("Daily jobs failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Daily jobs failed",
        ) from exc


@app.get("/scheduler-status")
def scheduler_status(
    job_manager: JobManager = Depends(get_job_manager),
) -> dict[str, object]:
    scheduler_data = scheduler_snapshot(app.state.scheduler)
    return {
        **scheduler_data,
        "database": job_manager.scheduler_status(),
    }
