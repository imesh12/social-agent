from pathlib import Path

from fastapi import Depends
from fastapi.testclient import TestClient
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
from database.models import Audio, Script, Topic, TopicStatus, Video
from services.ffmpeg_service import FFmpegService
from services.google_trends_service import GoogleTrendsService
from services.image_service import ImageService
from services.reddit_service import RedditService
from services.subtitle_service import SubtitleService
from services.thumbnail_service import ThumbnailService
from services.tts_service import TTSService
from services.youtube_service import YouTubeService
from tests.fake_llm import FakeLLMService


class FakeFFmpegService(FFmpegService):
    def create_video_from_image_and_audio(
        self,
        image_path: str,
        audio_path: str,
        output_path: str,
        width: int = 1080,
        height: int = 1920,
    ) -> None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"fake-mp4")


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
            ffmpeg_service=FakeFFmpegService(),
            image_service=ImageService(),
        ),
        subtitle_agent=SubtitleAgent(db=db, subtitle_service=SubtitleService()),
        seo_agent=SEOAgent(db=db, llm_service=FakeLLMService()),
        thumbnail_agent=ThumbnailAgent(db=db, thumbnail_service=ThumbnailService()),
        publisher_agent=PublisherAgent(db=db, youtube_service=YouTubeService()),
    )


def create_audio(audio_path: str) -> Audio:
    Path(audio_path).parent.mkdir(parents=True, exist_ok=True)
    Path(audio_path).write_bytes(b"fake-mp3")

    db = SessionLocal()
    try:
        topic = Topic(title="AI Tools", score=90, status=TopicStatus.SCRIPTED)
        script = Script(topic=topic, content='Hook:\n"Test hook"\n\nBody:\n"Test body"\n\nEnding:\n"Test ending"')
        audio = Audio(script=script, path=audio_path)
        db.add(audio)
        db.commit()
        db.refresh(audio)
        return audio
    finally:
        db.close()


def test_generate_video() -> None:
    app.dependency_overrides[get_manager_agent] = override_manager_agent
    try:
        with TestClient(app) as client:
            audio = create_audio("storage/audio/test_video_audio.mp3")
            response = client.post("/generate-video", json={"audio_id": audio.id})

        assert response.status_code == 200
        assert response.json() == {"video_path": f"storage/videos/video_{audio.id}.mp4"}
        assert Path(f"storage/videos/video_{audio.id}.mp4").exists()

        db = SessionLocal()
        try:
            video = db.query(Video).filter(Video.audio_id == audio.id).one()
            assert video.path == f"storage/videos/video_{audio.id}.mp4"
        finally:
            db.close()
    finally:
        app.dependency_overrides.clear()


def test_generate_video_returns_404_for_missing_audio() -> None:
    app.dependency_overrides[get_manager_agent] = override_manager_agent
    try:
        with TestClient(app) as client:
            response = client.post("/generate-video", json={"audio_id": 999999})

        assert response.status_code == 404
        assert response.json()["detail"] == "Audio 999999 was not found"
    finally:
        app.dependency_overrides.clear()
