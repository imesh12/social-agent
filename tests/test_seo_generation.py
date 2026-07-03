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
from database.models import Audio, SEO, Script, Topic, TopicStatus, Video
from services.ffmpeg_service import FFmpegService
from services.google_trends_service import GoogleTrendsService
from services.image_service import ImageService
from services.llm.base_llm_service import LLMSEOResult
from services.reddit_service import RedditService
from services.seo_intelligence_service import SEOIntelligenceResult, SEOIntelligenceService
from services.subtitle_service import SubtitleService
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
        audio = Audio(script=script, path="storage/audio/seo_test_audio.mp3")
        video = Video(audio=audio, path="storage/videos/seo_test_video.mp4")
        db.add(video)
        db.commit()
        db.refresh(video)
        return video
    finally:
        db.close()


def seo_score(score: int, title: str = "Top 3 AI Tools You Need In 2026 #shorts") -> SEOIntelligenceResult:
    return SEOIntelligenceResult(
        overall_score=score,
        title_score=score,
        description_score=score,
        keyword_score=score,
        tag_score=score,
        hashtag_score=score,
        search_intent_score=score,
        ctr_prediction=score,
        competition_level="medium",
        readability_score=score,
        engagement_score=score,
        recommended_title=title,
        recommended_description="Improved description.",
        recommended_tags=["AI", "Tools", "Productivity"],
        recommended_hashtags="#ai #shorts #tools",
        strengths=["clear intent"],
        weaknesses=["needs specificity"],
        recommended_changes=["tighten title"],
        accepted=score >= 85,
        attempt=0,
        analysis_timestamp="2026-06-30T00:00:00+00:00",
        fallback_used=False,
    )


def test_generate_seo() -> None:
    app.dependency_overrides[get_manager_agent] = override_manager_agent
    try:
        with TestClient(app) as client:
            video = create_video()
            response = client.post("/generate-seo", json={"video_id": video.id})

        assert response.status_code == 200
        assert response.json() == {
            "title": "Top 3 AI Tools You Need In 2026 #shorts",
            "description": "Discover AI tools changing productivity.",
            "tags": ["AI", "ChatGPT", "Technology"],
            "hashtags": "#ai #shorts #technology",
        }

        db = SessionLocal()
        try:
            seo = db.query(SEO).filter(SEO.video_id == video.id).one()
            assert seo.title == "Top 3 AI Tools You Need In 2026 #shorts"
            assert seo.hashtags == "#ai #shorts #technology"
        finally:
            db.close()
    finally:
        app.dependency_overrides.clear()


def test_generate_seo_returns_404_for_missing_video() -> None:
    app.dependency_overrides[get_manager_agent] = override_manager_agent
    try:
        with TestClient(app) as client:
            response = client.post("/generate-seo", json={"video_id": 999999})

        assert response.status_code == 404
        assert response.json()["detail"] == "Video 999999 was not found"
    finally:
        app.dependency_overrides.clear()


def test_seo_agent_runs_intelligence_and_accepts_high_score() -> None:
    video = create_video()
    llm = FakeLLMService(seo_score_sequence=[seo_score(90)])
    db = SessionLocal()
    try:
        agent = SEOAgent(
            db=db,
            llm_service=llm,
            seo_intelligence_service=SEOIntelligenceService(llm),
        )
        seo = agent.generate_seo(video_id=video.id)

        metadata = agent.metadata_service.load_seo_intelligence(video.id)
        assert seo.title == "Top 3 AI Tools You Need In 2026 #shorts"
        assert llm.seo_intelligence_calls == 1
        assert metadata["overall_score"] == 90
        assert metadata["accepted"] is True
    finally:
        db.close()


def test_seo_agent_improves_low_scoring_seo_and_saves_best() -> None:
    video = create_video()
    improved = LLMSEOResult(
        title="Specific AI Workflow Tools For Creators #shorts",
        description="A sharper AI tools description.",
        tags=["AI", "Workflow", "Creators"],
        hashtags="#ai #shorts #workflow",
    )
    llm = FakeLLMService(
        seo_score_sequence=[seo_score(70), seo_score(91, improved.title)],
        improved_seo_sequence=[improved],
    )
    db = SessionLocal()
    try:
        agent = SEOAgent(
            db=db,
            llm_service=llm,
            seo_intelligence_service=SEOIntelligenceService(llm),
        )
        seo = agent.generate_seo(video_id=video.id)

        metadata = agent.metadata_service.load_seo_intelligence(video.id)
        assert seo.title == "Specific AI Workflow Tools For Creators #shorts"
        assert llm.seo_improvement_calls == 1
        assert metadata["overall_score"] == 91
        assert metadata["attempt"] == 1
    finally:
        db.close()
