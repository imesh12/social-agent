from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from agents.manager_agent import ManagerAgent
from agents.publisher_agent import PublisherAgent
from agents.research_agent import ResearchAgent
from agents.script_agent import ScriptAgent
from agents.seo_agent import SEOAgent
from agents.subtitle_agent import SubtitleAgent
from agents.thumbnail_agent import ThumbnailAgent
from agents.trend_agent import TrendAgent
from agents.video_agent import VideoAgent
from agents.voice_agent import VoiceAgent
from backend.main import app
from backend.main import get_manager_agent
from database.database import get_db
from fastapi import Depends
from services.ffmpeg_service import FFmpegService
from services.image_service import ImageService
from services.subtitle_service import SubtitleService
from services.thumbnail_service import ThumbnailService
from services.trend_ranker_service import TrendRankerService
from services.tts_service import TTSService
from services.youtube_service import YouTubeService
from tests.fake_llm import FakeLLMService


class EmptyTrendSource:
    def fetch_trending_searches(self) -> list[str]:
        return []

    def fetch_titles(self) -> list[str]:
        return []

    def fetch_top_stories(self) -> list[str]:
        return []

    def fetch_headlines(self) -> list[str]:
        return []


def override_manager_agent(db: Session = Depends(get_db)) -> ManagerAgent:
    empty_source = EmptyTrendSource()
    return ManagerAgent(
        db=db,
        trend_agent=TrendAgent(
            reddit_service=empty_source,
            google_trends_service=empty_source,
            hacker_news_service=empty_source,
            news_api_service=empty_source,
            trend_ranker_service=TrendRankerService(),
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


def test_generate_topic() -> None:
    app.dependency_overrides[get_manager_agent] = override_manager_agent
    try:
        with TestClient(app) as client:
            response = client.post("/generate-topic")

        assert response.status_code == 200
        assert response.json() == {"topic": "AI Tools", "score": 90}
    finally:
        app.dependency_overrides.clear()


def test_generate_script() -> None:
    app.dependency_overrides[get_manager_agent] = override_manager_agent
    try:
        with TestClient(app) as client:
            response = client.post("/generate-script")

        assert response.status_code == 200
        payload = response.json()
        assert "Hook:" in payload["script"]
        assert "Body:" in payload["script"]
        assert "Ending:" in payload["script"]
    finally:
        app.dependency_overrides.clear()
