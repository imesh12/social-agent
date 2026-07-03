from pathlib import Path

from fastapi import Depends
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from agents.manager_agent import ManagerAgent
from agents.publisher_agent import PublisherAgent
from agents.research_agent import ResearchAgent
from agents.seo_agent import SEOAgent
from agents.script_agent import ScriptAgent
from agents.subtitle_agent import SubtitleAgent
from agents.thumbnail_agent import ThumbnailAgent
from agents.trend_agent import TrendAgent
from agents.video_agent import VideoAgent
from agents.voice_agent import VoiceAgent
from backend.main import app, get_manager_agent
from database.database import SessionLocal, get_db
from database.models import Audio, Script, Thumbnail, Topic, TopicStatus, Video
from services.ffmpeg_service import FFmpegService
from services.google_trends_service import GoogleTrendsService
from services.image_service import ImageService
from services.reddit_service import RedditService
from services.subtitle_service import SubtitleService
from services.thumbnail_intelligence_service import ThumbnailIntelligenceResult, ThumbnailIntelligenceService
from services.thumbnail_service import ThumbnailService
from services.tts_service import TTSService
from services.youtube_service import YouTubeService
from tests.fake_llm import FakeLLMService


def override_manager_agent(db: Session = Depends(get_db)) -> ManagerAgent:
    return ManagerAgent(
        db=db,
        trend_agent=TrendAgent(
            reddit_service=RedditService(),
            google_trends_service=GoogleTrendsService(),
        ),
        research_agent=ResearchAgent(llm_service=FakeLLMService()),
        script_agent=ScriptAgent(llm_service=FakeLLMService()),
        voice_agent=VoiceAgent(db=db, tts_service=TTSService()),
        video_agent=VideoAgent(
            db=db,
            ffmpeg_service=FFmpegService(),
            image_service=ImageService(),
        ),
        subtitle_agent=SubtitleAgent(db=db, subtitle_service=SubtitleService()),
        seo_agent=SEOAgent(db=db, llm_service=FakeLLMService()),
        thumbnail_agent=ThumbnailAgent(db=db, thumbnail_service=ThumbnailService()),
        publisher_agent=PublisherAgent(db=db, youtube_service=YouTubeService()),
    )


def create_video() -> Video:
    db = SessionLocal()
    try:
        topic = Topic(title="AI Tools", score=90, status=TopicStatus.SCRIPTED)
        script = Script(topic=topic, content="AI tools are changing productivity.")
        audio = Audio(script=script, path="storage/audio/thumb_test_audio.mp3")
        video = Video(audio=audio, path="storage/videos/thumb_test_video.mp4")
        db.add(video)
        db.commit()
        db.refresh(video)
        return video
    finally:
        db.close()


class CountingThumbnailService(ThumbnailService):
    def __init__(self) -> None:
        self.calls = 0

    def generate_thumbnail(self, output_path: str, width: int = 1280, height: int = 720) -> None:
        self.calls += 1
        super().generate_thumbnail(output_path=output_path, width=width, height=height)


def thumbnail_score(score: int) -> ThumbnailIntelligenceResult:
    return ThumbnailIntelligenceResult(
        overall_score=score,
        ctr_prediction=score,
        curiosity_score=score,
        emotion_score=score,
        contrast_score=score,
        visual_clarity=score,
        mobile_visibility=score,
        text_readability=score,
        subject_focus=score,
        brand_consistency=score,
        recommended_changes=["increase subject focus"],
        strengths=["clear text"],
        weaknesses=["needs more contrast"],
        regeneration_attempt=0,
        accepted=score >= 85,
        selected_thumbnail_path="",
        analysis_timestamp="2026-06-30T00:00:00+00:00",
        fallback_used=False,
    )


def test_generate_thumbnail() -> None:
    app.dependency_overrides[get_manager_agent] = override_manager_agent
    try:
        with TestClient(app) as client:
            video = create_video()
            response = client.post("/generate-thumbnail", json={"video_id": video.id})

        expected_path = f"storage/thumbnails/thumb_{video.id}.jpg"
        assert response.status_code == 200
        assert response.json() == {"thumbnail_path": expected_path}
        assert Path(expected_path).exists()

        with Image.open(expected_path) as image:
            assert image.size == (1280, 720)

        db = SessionLocal()
        try:
            thumbnail = db.query(Thumbnail).filter(Thumbnail.video_id == video.id).one()
            assert thumbnail.path == expected_path
        finally:
            db.close()
    finally:
        app.dependency_overrides.clear()


def test_generate_thumbnail_returns_404_for_missing_video() -> None:
    app.dependency_overrides[get_manager_agent] = override_manager_agent
    try:
        with TestClient(app) as client:
            response = client.post("/generate-thumbnail", json={"video_id": 999999})

        assert response.status_code == 404
        assert response.json()["detail"] == "Video 999999 was not found"
    finally:
        app.dependency_overrides.clear()


def test_thumbnail_agent_regenerates_when_score_is_low() -> None:
    video = create_video()
    thumbnail_service = CountingThumbnailService()
    llm = FakeLLMService(thumbnail_score_sequence=[thumbnail_score(70), thumbnail_score(90)])
    intelligence_service = ThumbnailIntelligenceService(llm_service=llm)

    db = SessionLocal()
    try:
        agent = ThumbnailAgent(
            db=db,
            thumbnail_service=thumbnail_service,
            thumbnail_intelligence_service=intelligence_service,
        )
        thumbnail = agent.generate_thumbnail(video_id=video.id)

        metadata = agent.metadata_service.load_thumbnail_intelligence(video.id)
        assert thumbnail_service.calls == 2
        assert thumbnail.path == f"storage/thumbnails/thumb_{video.id}.jpg"
        assert metadata["overall_score"] == 90
        assert metadata["regeneration_attempt"] == 1
        assert metadata["accepted"] is True
    finally:
        db.close()


def test_thumbnail_agent_respects_max_attempts_and_selects_highest_score() -> None:
    video = create_video()
    thumbnail_service = CountingThumbnailService()
    llm = FakeLLMService(thumbnail_score_sequence=[thumbnail_score(70), thumbnail_score(80), thumbnail_score(75)])
    intelligence_service = ThumbnailIntelligenceService(llm_service=llm)

    db = SessionLocal()
    try:
        agent = ThumbnailAgent(
            db=db,
            thumbnail_service=thumbnail_service,
            thumbnail_intelligence_service=intelligence_service,
        )
        agent.generate_thumbnail(video_id=video.id)

        metadata = agent.metadata_service.load_thumbnail_intelligence(video.id)
        assert thumbnail_service.calls == 3
        assert metadata["overall_score"] == 80
        assert metadata["regeneration_attempt"] == 1
        assert metadata["accepted"] is False
    finally:
        db.close()


def test_thumbnail_agent_fails_soft_when_intelligence_fails() -> None:
    video = create_video()
    thumbnail_service = CountingThumbnailService()
    intelligence_service = ThumbnailIntelligenceService(
        llm_service=FakeLLMService(fail_thumbnail_intelligence=True)
    )

    db = SessionLocal()
    try:
        agent = ThumbnailAgent(
            db=db,
            thumbnail_service=thumbnail_service,
            thumbnail_intelligence_service=intelligence_service,
        )
        thumbnail = agent.generate_thumbnail(video_id=video.id)

        metadata = agent.metadata_service.load_thumbnail_intelligence(video.id)
        assert Path(thumbnail.path).exists()
        assert metadata["fallback_used"] is True
        assert metadata["recommended_changes"]
    finally:
        db.close()
