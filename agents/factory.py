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
from services.competitor_analysis_service import CompetitorAnalysisService
from services.content_intelligence_service import ContentIntelligenceService
from services.fact_verification_service import FactVerificationService
from services.google_trends_service import GoogleTrendsService
from services.hook_intelligence_service import HookIntelligenceService
from services.image_service import ImageService
from services.llm.factory import build_llm_service
from services.news_service import HackerNewsService, NewsAPIService
from services.pipeline_state_service import PipelineStateMachine
from services.publisher_decision_service import PublisherDecisionService
from services.reddit_service import RedditService
from services.seo_intelligence_service import SEOIntelligenceService
from services.subtitle_service import SubtitleService
from services.thumbnail_service import ThumbnailService
from services.thumbnail_intelligence_service import ThumbnailIntelligenceService
from services.tts_service import TTSService
from services.trend_ranker_service import TrendRankerService
from services.youtube_service import YouTubeService
from services.viral_prediction_service import ViralPredictionService


def build_manager_agent(db: Session) -> ManagerAgent:
    llm_service = build_llm_service()
    reddit_service = RedditService()
    hacker_news_service = HackerNewsService()
    news_api_service = NewsAPIService()
    pipeline_state = PipelineStateMachine(db)
    return ManagerAgent(
        db=db,
        trend_agent=TrendAgent(
            reddit_service=reddit_service,
            google_trends_service=GoogleTrendsService(),
            hacker_news_service=hacker_news_service,
            news_api_service=news_api_service,
            trend_ranker_service=TrendRankerService(),
        ),
        research_agent=ResearchAgent(
            llm_service=llm_service,
            competitor_analysis_service=CompetitorAnalysisService(
                reddit_service=reddit_service,
                hacker_news_service=hacker_news_service,
                news_api_service=news_api_service,
                llm_service=llm_service,
            ),
            fact_verification_service=FactVerificationService(news_api_service=news_api_service),
        ),
        script_agent=ScriptAgent(
            llm_service=llm_service,
            hook_intelligence_service=HookIntelligenceService(),
            content_intelligence_service=ContentIntelligenceService(llm_service),
        ),
        voice_agent=VoiceAgent(db=db, tts_service=TTSService()),
        video_agent=VideoAgent(
            db=db,
            ffmpeg_service=FFmpegService(),
            image_service=ImageService(),
        ),
        subtitle_agent=SubtitleAgent(db=db, subtitle_service=SubtitleService()),
        seo_agent=SEOAgent(
            db=db,
            llm_service=llm_service,
            seo_intelligence_service=SEOIntelligenceService(llm_service),
        ),
        thumbnail_agent=ThumbnailAgent(
            db=db,
            thumbnail_service=ThumbnailService(),
            thumbnail_intelligence_service=ThumbnailIntelligenceService(llm_service),
        ),
        publisher_agent=PublisherAgent(
            db=db,
            youtube_service=YouTubeService(),
            viral_prediction_service=ViralPredictionService(llm_service),
            publisher_decision_service=PublisherDecisionService(llm_service),
        ),
        pipeline_state=pipeline_state,
    )
