from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.database import Base


class TopicStatus(StrEnum):
    NEW = "new"
    SCRIPTED = "scripted"


class AudioStatus(StrEnum):
    GENERATED = "generated"
    FAILED = "failed"


class VideoStatus(StrEnum):
    GENERATED = "generated"
    FAILED = "failed"


class SubtitleStatus(StrEnum):
    GENERATED = "generated"
    FAILED = "failed"


class PublishJobStatus(StrEnum):
    UPLOADED = "uploaded"
    FAILED = "failed"


class ScheduledJobStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineStage(StrEnum):
    NEW = "new"
    RESEARCHING = "researching"
    RESEARCH_READY = "research_ready"
    SCRIPT_GENERATING = "script_generating"
    SCRIPT_READY = "script_ready"
    AUDIO_GENERATING = "audio_generating"
    AUDIO_READY = "audio_ready"
    VIDEO_GENERATING = "video_generating"
    VIDEO_READY = "video_ready"
    SUBTITLE_GENERATING = "subtitle_generating"
    SUBTITLE_READY = "subtitle_ready"
    THUMBNAIL_GENERATING = "thumbnail_generating"
    THUMBNAIL_READY = "thumbnail_ready"
    SEO_GENERATING = "seo_generating"
    SEO_READY = "seo_ready"
    READY_FOR_UPLOAD = "ready_for_upload"
    UPLOADING = "uploading"
    VERIFYING_UPLOAD = "verifying_upload"
    PUBLISHED = "published"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class PipelineTaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[TopicStatus] = mapped_column(
        Enum(TopicStatus),
        default=TopicStatus.NEW,
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    scripts: Mapped[list["Script"]] = relationship(
        back_populates="topic",
        cascade="all, delete-orphan",
    )
    pipeline_tasks: Mapped[list["PipelineTask"]] = relationship(
        back_populates="topic",
    )


class Script(Base):
    __tablename__ = "scripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    topic: Mapped[Topic] = relationship(back_populates="scripts")
    audios: Mapped[list["Audio"]] = relationship(
        back_populates="script",
        cascade="all, delete-orphan",
    )


class Audio(Base):
    __tablename__ = "audios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    script_id: Mapped[int] = mapped_column(ForeignKey("scripts.id"), nullable=False, index=True)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[AudioStatus] = mapped_column(
        Enum(AudioStatus),
        default=AudioStatus.GENERATED,
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    script: Mapped[Script] = relationship(back_populates="audios")
    videos: Mapped[list["Video"]] = relationship(
        back_populates="audio",
        cascade="all, delete-orphan",
    )


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    audio_id: Mapped[int] = mapped_column(ForeignKey("audios.id"), nullable=False, index=True)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[VideoStatus] = mapped_column(
        Enum(VideoStatus),
        default=VideoStatus.GENERATED,
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    audio: Mapped[Audio] = relationship(back_populates="videos")
    subtitles: Mapped[list["Subtitle"]] = relationship(
        back_populates="video",
        cascade="all, delete-orphan",
    )
    publish_jobs: Mapped[list["PublishJob"]] = relationship(
        back_populates="video",
        cascade="all, delete-orphan",
    )
    seo_records: Mapped[list["SEO"]] = relationship(
        back_populates="video",
        cascade="all, delete-orphan",
    )
    thumbnails: Mapped[list["Thumbnail"]] = relationship(
        back_populates="video",
        cascade="all, delete-orphan",
    )
    pipeline_tasks: Mapped[list["PipelineTask"]] = relationship(
        back_populates="video",
    )


class Subtitle(Base):
    __tablename__ = "subtitles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), nullable=False, index=True)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[SubtitleStatus] = mapped_column(
        Enum(SubtitleStatus),
        default=SubtitleStatus.GENERATED,
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    video: Mapped[Video] = relationship(back_populates="subtitles")


class SEO(Base):
    __tablename__ = "seo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[str] = mapped_column(Text, nullable=False)
    hashtags: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    video: Mapped[Video] = relationship(back_populates="seo_records")


class Thumbnail(Base):
    __tablename__ = "thumbnails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), nullable=False, index=True)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    video: Mapped[Video] = relationship(back_populates="thumbnails")


class PublishJob(Base):
    __tablename__ = "publish_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    youtube_video_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    youtube_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[PublishJobStatus] = mapped_column(
        Enum(PublishJobStatus),
        default=PublishJobStatus.UPLOADED,
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    video: Mapped[Video] = relationship(back_populates="publish_jobs")


class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[ScheduledJobStatus] = mapped_column(
        Enum(ScheduledJobStatus),
        default=ScheduledJobStatus.RUNNING,
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PipelineTask(Base):
    __tablename__ = "pipeline_tasks"
    __table_args__ = (
        UniqueConstraint("task_uuid", name="uq_pipeline_tasks_task_uuid"),
        Index("ix_pipeline_tasks_stage_status", "current_stage", "status"),
        Index("ix_pipeline_tasks_updated_at", "updated_at"),
        Index("ix_pipeline_tasks_topic_stage", "topic_id", "current_stage"),
        Index("ix_pipeline_tasks_video_stage", "video_id", "current_stage"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    task_uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id"), nullable=True, index=True)
    video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id"), nullable=True, index=True)
    current_stage: Mapped[PipelineStage] = mapped_column(
        Enum(PipelineStage),
        default=PipelineStage.NEW,
        nullable=False,
        index=True,
    )
    status: Mapped[PipelineTaskStatus] = mapped_column(
        Enum(PipelineTaskStatus),
        default=PipelineTaskStatus.PENDING,
        nullable=False,
        index=True,
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_traceback: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    topic: Mapped[Topic | None] = relationship(back_populates="pipeline_tasks")
    video: Mapped[Video | None] = relationship(back_populates="pipeline_tasks")
