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
from services.ffmpeg_service import FFmpegService
from services.google_trends_service import GoogleTrendsService
from services.image_service import ImageService
from services.llm.factory import build_llm_service
from services.news_service import HackerNewsService, NewsAPIService
from services.reddit_service import RedditService
from services.subtitle_service import SubtitleService
from services.thumbnail_service import ThumbnailService
from services.tts_service import TTSService
from services.trend_ranker_service import TrendRankerService
from services.youtube_service import YouTubeService


def build_manager_agent(db: Session) -> ManagerAgent:
    llm_service = build_llm_service()
    return ManagerAgent(
        db=db,
        trend_agent=TrendAgent(
            reddit_service=RedditService(),
            google_trends_service=GoogleTrendsService(),
            hacker_news_service=HackerNewsService(),
            news_api_service=NewsAPIService(),
            trend_ranker_service=TrendRankerService(),
        ),
        research_agent=ResearchAgent(llm_service=llm_service),
        script_agent=ScriptAgent(llm_service=llm_service),
        voice_agent=VoiceAgent(db=db, tts_service=TTSService()),
        video_agent=VideoAgent(
            db=db,
            ffmpeg_service=FFmpegService(),
            image_service=ImageService(),
        ),
        subtitle_agent=SubtitleAgent(db=db, subtitle_service=SubtitleService()),
        seo_agent=SEOAgent(db=db, llm_service=llm_service),
        thumbnail_agent=ThumbnailAgent(db=db, thumbnail_service=ThumbnailService()),
        publisher_agent=PublisherAgent(db=db, youtube_service=YouTubeService()),
    )
