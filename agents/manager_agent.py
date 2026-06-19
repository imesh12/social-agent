import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.publisher_agent import PublisherAgent
from agents.research_agent import ResearchAgent
from agents.seo_agent import SEOAgent
from agents.script_agent import ScriptAgent
from agents.subtitle_agent import SubtitleAgent
from agents.thumbnail_agent import ThumbnailAgent
from agents.trend_agent import TrendAgent
from agents.video_agent import VideoAgent
from agents.voice_agent import VoiceAgent
from database.models import Audio, PublishJob, Script, SEO, Subtitle, Thumbnail, Topic, TopicStatus, Video

logger = logging.getLogger(__name__)


class ManagerAgent:
    def __init__(
        self,
        db: Session,
        trend_agent: TrendAgent,
        research_agent: ResearchAgent,
        script_agent: ScriptAgent,
        voice_agent: VoiceAgent,
        video_agent: VideoAgent,
        subtitle_agent: SubtitleAgent,
        seo_agent: SEOAgent,
        thumbnail_agent: ThumbnailAgent,
        publisher_agent: PublisherAgent,
    ) -> None:
        self.db = db
        self.trend_agent = trend_agent
        self.research_agent = research_agent
        self.script_agent = script_agent
        self.voice_agent = voice_agent
        self.video_agent = video_agent
        self.subtitle_agent = subtitle_agent
        self.seo_agent = seo_agent
        self.thumbnail_agent = thumbnail_agent
        self.publisher_agent = publisher_agent

    def generate_topic(self) -> Topic:
        trend = self.trend_agent.find_trending_topic()
        topic = Topic(title=trend.topic, score=trend.score, status=TopicStatus.NEW)
        self.db.add(topic)
        self.db.commit()
        self.db.refresh(topic)
        logger.info("Generated topic id=%s title=%s score=%s", topic.id, topic.title, topic.score)
        return topic

    def generate_script(self) -> Script:
        topic = self._get_latest_topic() or self.generate_topic()
        research = self.research_agent.research_topic(topic.title)
        script_result = self.script_agent.create_script(research)
        script = Script(topic_id=topic.id, content=script_result.content)
        topic.status = TopicStatus.SCRIPTED
        self.db.add(script)
        self.db.commit()
        self.db.refresh(script)
        logger.info("Generated script id=%s topic_id=%s", script.id, topic.id)
        return script

    def _get_latest_topic(self) -> Topic | None:
        statement = select(Topic).order_by(Topic.created_at.desc())
        return self.db.scalars(statement).first()

    async def generate_audio(self, script_id: int, voice: str = "en-US-JennyNeural") -> Audio:
        return await self.voice_agent.generate_audio(script_id=script_id, voice=voice)

    def generate_video(self, audio_id: int) -> Video:
        return self.video_agent.generate_video(audio_id=audio_id)

    def generate_subtitles(self, video_id: int) -> Subtitle:
        return self.subtitle_agent.generate_subtitles(video_id=video_id)

    def generate_seo(self, video_id: int) -> SEO:
        return self.seo_agent.generate_seo(video_id=video_id)

    def generate_thumbnail(self, video_id: int) -> Thumbnail:
        return self.thumbnail_agent.generate_thumbnail(video_id=video_id)

    def publish_youtube(self, video_id: int) -> PublishJob:
        return self.publisher_agent.publish_youtube(video_id=video_id)
