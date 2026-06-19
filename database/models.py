from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
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
