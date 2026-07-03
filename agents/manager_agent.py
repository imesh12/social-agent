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
from database.models import Audio, PipelineStage, PublishJob, Script, SEO, Subtitle, Thumbnail, Topic, TopicStatus, Video
from services.metadata_service import GenerationMetadataService
from services.pipeline_state_service import PipelineStateMachine

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
        pipeline_state: PipelineStateMachine | None = None,
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
        self.metadata_service = GenerationMetadataService()
        self.pipeline_state = pipeline_state or PipelineStateMachine(db)

    def generate_topic(self) -> Topic:
        trend = self.trend_agent.find_trending_topic()
        topic = Topic(title=trend.topic, score=trend.score, status=TopicStatus.NEW)
        self.db.add(topic)
        self.db.commit()
        self.db.refresh(topic)
        task = self.pipeline_state.create_task(
            topic_id=topic.id,
            current_stage=PipelineStage.NEW,
            metadata={"topic": topic.title, "topic_id": topic.id},
        )
        self.pipeline_state.update_metadata(task, {"score": topic.score})
        logger.info("Generated topic id=%s title=%s score=%s", topic.id, topic.title, topic.score)
        return topic

    def generate_script(self) -> Script:
        topic = self._get_latest_topic() or self.generate_topic()
        task = self.pipeline_state.task_for_topic(topic.id) or self.pipeline_state.create_task(
            topic_id=topic.id,
            current_stage=PipelineStage.NEW,
            metadata={"topic": topic.title, "topic_id": topic.id},
        )
        try:
            if task.current_stage == PipelineStage.NEW:
                self.pipeline_state.claim(task, PipelineStage.RESEARCHING, PipelineStage.NEW)
                research = self.research_agent.research_topic(topic.title)
                self.pipeline_state.transition(
                    task,
                    PipelineStage.RESEARCH_READY,
                    expected=PipelineStage.RESEARCHING,
                    metadata={"research_topic": research.topic},
                )
            else:
                research = self.research_agent.research_topic(topic.title)
            self.pipeline_state.claim(task, PipelineStage.SCRIPT_GENERATING, PipelineStage.RESEARCH_READY)
            script_result = self.script_agent.create_script(research)
            script = Script(topic_id=topic.id, content=script_result.content)
            topic.status = TopicStatus.SCRIPTED
            self.db.add(script)
            self.db.commit()
            self.db.refresh(script)
            self.pipeline_state.transition(
                task,
                PipelineStage.SCRIPT_READY,
                expected=PipelineStage.SCRIPT_GENERATING,
                metadata={"script_id": script.id},
            )
            self.metadata_service.save_script_quality(
                script_id=script.id,
                score=script_result.score,
                accepted=script_result.accepted,
                regenerated=script_result.regenerated,
                attempt_count=script_result.attempt_count,
            )
            self.metadata_service.save_script_variants(
                script_id=script.id,
                selection=script_result.version_selection,
            )
            self.metadata_service.save_hook_intelligence(
                script_id=script.id,
                hook_selection=script_result.hook_selection,
            )
            self.metadata_service.save_content_intelligence(
                script_id=script.id,
                analysis=script_result.content_intelligence,
            )
            self.metadata_service.save_research_intelligence(
                script_id=script.id,
                competitor_analysis=research.competitor_analysis,
            )
            self.metadata_service.save_fact_verification(
                script_id=script.id,
                fact_verification=research.fact_verification,
            )
            logger.info("Generated script id=%s topic_id=%s", script.id, topic.id)
            return script
        except Exception as exc:
            self.pipeline_state.mark_retry_or_failed(task, exc)
            raise

    def _get_latest_topic(self) -> Topic | None:
        statement = select(Topic).order_by(Topic.created_at.desc())
        return self.db.scalars(statement).first()

    async def generate_audio(self, script_id: int, voice: str = "en-US-JennyNeural") -> Audio:
        if self.db.get(Script, script_id) is None:
            return await self.voice_agent.generate_audio(script_id=script_id, voice=voice)
        task = self.pipeline_state.adopt_script(script_id)
        try:
            self.pipeline_state.claim(task, PipelineStage.AUDIO_GENERATING, PipelineStage.SCRIPT_READY)
            audio = await self.voice_agent.generate_audio(script_id=script_id, voice=voice)
            self.pipeline_state.transition(
                task,
                PipelineStage.AUDIO_READY,
                expected=PipelineStage.AUDIO_GENERATING,
                metadata={"audio_id": audio.id},
            )
            return audio
        except Exception as exc:
            self.pipeline_state.mark_retry_or_failed(task, exc)
            raise

    def generate_video(self, audio_id: int) -> Video:
        if self.db.get(Audio, audio_id) is None:
            return self.video_agent.generate_video(audio_id=audio_id)
        task = self.pipeline_state.adopt_audio(audio_id)
        try:
            self.pipeline_state.claim(task, PipelineStage.VIDEO_GENERATING, PipelineStage.AUDIO_READY)
            video = self.video_agent.generate_video(audio_id=audio_id)
            self.pipeline_state.transition(
                task,
                PipelineStage.VIDEO_READY,
                expected=PipelineStage.VIDEO_GENERATING,
                metadata={"video_id": video.id},
            )
            return video
        except Exception as exc:
            self.pipeline_state.mark_retry_or_failed(task, exc)
            raise

    def generate_subtitles(self, video_id: int) -> Subtitle:
        if self.db.get(Video, video_id) is None:
            return self.subtitle_agent.generate_subtitles(video_id=video_id)
        task = self.pipeline_state.adopt_video(video_id)
        try:
            self.pipeline_state.claim(task, PipelineStage.SUBTITLE_GENERATING, PipelineStage.VIDEO_READY)
            subtitle = self.subtitle_agent.generate_subtitles(video_id=video_id)
            self.pipeline_state.transition(
                task,
                PipelineStage.SUBTITLE_READY,
                expected=PipelineStage.SUBTITLE_GENERATING,
                metadata={"subtitle_id": subtitle.id},
            )
            return subtitle
        except Exception as exc:
            self.pipeline_state.mark_retry_or_failed(task, exc)
            raise

    def generate_seo(self, video_id: int) -> SEO:
        if self.db.get(Video, video_id) is None:
            return self.seo_agent.generate_seo(video_id=video_id)
        task = self.pipeline_state.adopt_video(video_id)
        try:
            previous_stage = task.current_stage
            self.pipeline_state.claim(
                task,
                PipelineStage.SEO_GENERATING,
                (PipelineStage.VIDEO_READY, PipelineStage.SUBTITLE_READY, PipelineStage.THUMBNAIL_READY),
            )
            seo = self.seo_agent.generate_seo(video_id=video_id)
            next_stage = PipelineStage.READY_FOR_UPLOAD if previous_stage == PipelineStage.THUMBNAIL_READY else PipelineStage.SEO_READY
            self.pipeline_state.transition(
                task,
                next_stage,
                expected=PipelineStage.SEO_GENERATING,
                metadata={"seo_id": seo.id},
            )
            return seo
        except Exception as exc:
            self.pipeline_state.mark_retry_or_failed(task, exc)
            raise

    def generate_thumbnail(self, video_id: int) -> Thumbnail:
        if self.db.get(Video, video_id) is None:
            return self.thumbnail_agent.generate_thumbnail(video_id=video_id)
        task = self.pipeline_state.adopt_video(video_id)
        try:
            self.pipeline_state.claim(
                task,
                PipelineStage.THUMBNAIL_GENERATING,
                (PipelineStage.VIDEO_READY, PipelineStage.SUBTITLE_READY, PipelineStage.SEO_READY),
            )
            thumbnail = self.thumbnail_agent.generate_thumbnail(video_id=video_id)
            self.pipeline_state.transition(
                task,
                PipelineStage.READY_FOR_UPLOAD,
                expected=PipelineStage.THUMBNAIL_GENERATING,
                metadata={"thumbnail_id": thumbnail.id},
            )
            return thumbnail
        except Exception as exc:
            self.pipeline_state.mark_retry_or_failed(task, exc)
            raise

    def publish_youtube(self, video_id: int) -> PublishJob:
        if self.db.get(Video, video_id) is None:
            return self.publisher_agent.publish_youtube(video_id=video_id)
        task = self.pipeline_state.adopt_video(video_id)
        try:
            self.pipeline_state.claim(
                task,
                PipelineStage.UPLOADING,
                (PipelineStage.READY_FOR_UPLOAD, PipelineStage.SEO_READY, PipelineStage.THUMBNAIL_READY, PipelineStage.VIDEO_READY),
            )
            publish_job = self.publisher_agent.publish_youtube(video_id=video_id)
            if getattr(publish_job.status, "value", "") == "failed":
                raise RuntimeError("YouTube upload failed")
            self.pipeline_state.transition(
                task,
                PipelineStage.VERIFYING_UPLOAD,
                expected=PipelineStage.UPLOADING,
                metadata={"publish_job_id": publish_job.id, "youtube_video_id": publish_job.youtube_video_id},
            )
            self.pipeline_state.transition(
                task,
                PipelineStage.PUBLISHED,
                expected=PipelineStage.VERIFYING_UPLOAD,
                metadata={"youtube_url": publish_job.youtube_url},
            )
            return publish_job
        except Exception as exc:
            self.pipeline_state.mark_retry_or_failed(task, exc)
            raise
