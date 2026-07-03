import json
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from database.models import (
    Audio,
    PipelineStage,
    PipelineTask,
    PipelineTaskStatus,
    Script,
    Topic,
    Video,
)
from services.utils.logging import get_rotating_logger

pipeline_logger = get_rotating_logger("pipeline_state", "pipeline_state.log")


class PipelineTransitionError(RuntimeError):
    """Raised when a pipeline task attempts an invalid state transition."""


class PipelineTaskNotFoundError(RuntimeError):
    """Raised when a pipeline task cannot be found for the requested resource."""


READY_STATUSES = {PipelineTaskStatus.PENDING, PipelineTaskStatus.READY, PipelineTaskStatus.RETRYING}
RUNNING_STAGES = {
    PipelineStage.RESEARCHING,
    PipelineStage.SCRIPT_GENERATING,
    PipelineStage.AUDIO_GENERATING,
    PipelineStage.VIDEO_GENERATING,
    PipelineStage.SUBTITLE_GENERATING,
    PipelineStage.THUMBNAIL_GENERATING,
    PipelineStage.SEO_GENERATING,
    PipelineStage.UPLOADING,
    PipelineStage.VERIFYING_UPLOAD,
}
TERMINAL_STAGES = {PipelineStage.PUBLISHED, PipelineStage.FAILED, PipelineStage.CANCELLED}

ALLOWED_TRANSITIONS: dict[PipelineStage, set[PipelineStage]] = {
    PipelineStage.NEW: {PipelineStage.RESEARCHING, PipelineStage.RETRYING, PipelineStage.FAILED, PipelineStage.CANCELLED},
    PipelineStage.RESEARCHING: {PipelineStage.RESEARCH_READY, PipelineStage.RETRYING, PipelineStage.FAILED},
    PipelineStage.RESEARCH_READY: {PipelineStage.SCRIPT_GENERATING, PipelineStage.RETRYING, PipelineStage.FAILED},
    PipelineStage.SCRIPT_GENERATING: {PipelineStage.SCRIPT_READY, PipelineStage.RETRYING, PipelineStage.FAILED},
    PipelineStage.SCRIPT_READY: {PipelineStage.AUDIO_GENERATING, PipelineStage.RETRYING, PipelineStage.FAILED},
    PipelineStage.AUDIO_GENERATING: {PipelineStage.AUDIO_READY, PipelineStage.RETRYING, PipelineStage.FAILED},
    PipelineStage.AUDIO_READY: {PipelineStage.VIDEO_GENERATING, PipelineStage.RETRYING, PipelineStage.FAILED},
    PipelineStage.VIDEO_GENERATING: {PipelineStage.VIDEO_READY, PipelineStage.RETRYING, PipelineStage.FAILED},
    PipelineStage.VIDEO_READY: {
        PipelineStage.SUBTITLE_GENERATING,
        PipelineStage.SEO_GENERATING,
        PipelineStage.THUMBNAIL_GENERATING,
        PipelineStage.UPLOADING,
        PipelineStage.RETRYING,
        PipelineStage.FAILED,
    },
    PipelineStage.SUBTITLE_GENERATING: {PipelineStage.SUBTITLE_READY, PipelineStage.RETRYING, PipelineStage.FAILED},
    PipelineStage.SUBTITLE_READY: {
        PipelineStage.THUMBNAIL_GENERATING,
        PipelineStage.SEO_GENERATING,
        PipelineStage.RETRYING,
        PipelineStage.FAILED,
    },
    PipelineStage.THUMBNAIL_GENERATING: {
        PipelineStage.THUMBNAIL_READY,
        PipelineStage.READY_FOR_UPLOAD,
        PipelineStage.RETRYING,
        PipelineStage.FAILED,
    },
    PipelineStage.THUMBNAIL_READY: {PipelineStage.SEO_GENERATING, PipelineStage.READY_FOR_UPLOAD, PipelineStage.RETRYING, PipelineStage.FAILED},
    PipelineStage.SEO_GENERATING: {PipelineStage.SEO_READY, PipelineStage.RETRYING, PipelineStage.FAILED},
    PipelineStage.SEO_READY: {PipelineStage.THUMBNAIL_GENERATING, PipelineStage.READY_FOR_UPLOAD, PipelineStage.RETRYING, PipelineStage.FAILED},
    PipelineStage.READY_FOR_UPLOAD: {PipelineStage.UPLOADING, PipelineStage.RETRYING, PipelineStage.FAILED, PipelineStage.CANCELLED},
    PipelineStage.UPLOADING: {PipelineStage.VERIFYING_UPLOAD, PipelineStage.RETRYING, PipelineStage.FAILED},
    PipelineStage.VERIFYING_UPLOAD: {PipelineStage.PUBLISHED, PipelineStage.RETRYING, PipelineStage.FAILED},
    PipelineStage.RETRYING: {
        PipelineStage.RESEARCHING,
        PipelineStage.SCRIPT_GENERATING,
        PipelineStage.AUDIO_GENERATING,
        PipelineStage.VIDEO_GENERATING,
        PipelineStage.SUBTITLE_GENERATING,
        PipelineStage.THUMBNAIL_GENERATING,
        PipelineStage.SEO_GENERATING,
        PipelineStage.UPLOADING,
        PipelineStage.FAILED,
        PipelineStage.CANCELLED,
    },
    PipelineStage.FAILED: {PipelineStage.RETRYING, PipelineStage.CANCELLED},
    PipelineStage.PUBLISHED: set(),
    PipelineStage.CANCELLED: set(),
}

PREVIOUS_READY_STAGE: dict[PipelineStage, PipelineStage] = {
    PipelineStage.RESEARCHING: PipelineStage.NEW,
    PipelineStage.SCRIPT_GENERATING: PipelineStage.RESEARCH_READY,
    PipelineStage.AUDIO_GENERATING: PipelineStage.SCRIPT_READY,
    PipelineStage.VIDEO_GENERATING: PipelineStage.AUDIO_READY,
    PipelineStage.SUBTITLE_GENERATING: PipelineStage.VIDEO_READY,
    PipelineStage.THUMBNAIL_GENERATING: PipelineStage.SEO_READY,
    PipelineStage.SEO_GENERATING: PipelineStage.SUBTITLE_READY,
    PipelineStage.UPLOADING: PipelineStage.READY_FOR_UPLOAD,
    PipelineStage.VERIFYING_UPLOAD: PipelineStage.READY_FOR_UPLOAD,
}


class PipelineStateMachine:
    """Persistent transactional state machine for content pipeline tasks."""

    def __init__(
        self,
        db: Session,
        worker_id: str | None = None,
        max_retries: int | None = None,
    ) -> None:
        settings = get_settings()
        self.db = db
        self.worker_id = worker_id or settings.pipeline_worker_id
        self.max_retries = max_retries if max_retries is not None else settings.pipeline_max_retries

    def create_task(
        self,
        *,
        topic_id: int | None = None,
        video_id: int | None = None,
        current_stage: PipelineStage = PipelineStage.NEW,
        status: PipelineTaskStatus | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PipelineTask:
        """Create and persist a new pipeline task."""
        now = self._now()
        task = PipelineTask(
            task_uuid=str(uuid.uuid4()),
            topic_id=topic_id,
            video_id=video_id,
            current_stage=current_stage,
            status=status or self._status_for_stage(current_stage),
            retry_count=0,
            worker_id=None,
            started_at=None,
            updated_at=now,
            completed_at=now if current_stage in TERMINAL_STAGES else None,
            metadata_json=json.dumps(metadata or {}),
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        self._log_transition(task, None, current_stage, 0.0, "created", None)
        return task

    def transition(
        self,
        task: PipelineTask,
        next_stage: PipelineStage,
        *,
        expected: PipelineStage | Iterable[PipelineStage] | None = None,
        metadata: dict[str, Any] | None = None,
        error: Exception | str | None = None,
    ) -> PipelineTask:
        """Atomically validate and persist a stage transition."""
        started = time.perf_counter()
        previous_stage = task.current_stage
        expected_set = self._expected_set(expected)
        if expected_set and previous_stage not in expected_set:
            raise PipelineTransitionError(
                f"Task {task.task_uuid} expected one of {[stage.value for stage in expected_set]} "
                f"but was {previous_stage.value}"
            )
        if next_stage not in ALLOWED_TRANSITIONS.get(previous_stage, set()) and next_stage != previous_stage:
            raise PipelineTransitionError(
                f"Invalid pipeline transition {previous_stage.value} -> {next_stage.value} "
                f"for task {task.task_uuid}"
            )

        try:
            now = self._now()
            task.current_stage = next_stage
            task.status = self._status_for_stage(next_stage)
            task.updated_at = now
            task.worker_id = self.worker_id if next_stage in RUNNING_STAGES else None
            if next_stage in RUNNING_STAGES and task.started_at is None:
                task.started_at = now
            if next_stage in TERMINAL_STAGES:
                task.completed_at = now
            if metadata:
                self.update_metadata(task, metadata, commit=False)
            if error is not None:
                task.last_error = str(error)
                task.last_traceback = traceback.format_exc() if not isinstance(error, str) else None
            elif next_stage not in {PipelineStage.FAILED, PipelineStage.RETRYING}:
                task.last_error = None
                task.last_traceback = None
            self.db.commit()
            self.db.refresh(task)
            self._log_transition(
                task,
                previous_stage,
                next_stage,
                time.perf_counter() - started,
                "transitioned",
                error,
            )
            return task
        except Exception as exc:
            self.db.rollback()
            pipeline_logger.exception(
                "Pipeline transition failed task_uuid=%s previous_stage=%s next_stage=%s worker=%s retry_count=%s",
                task.task_uuid,
                previous_stage.value,
                next_stage.value,
                self.worker_id,
                task.retry_count,
            )
            raise exc

    def mark_retry_or_failed(self, task: PipelineTask, exc: Exception) -> PipelineTask:
        """Record failure and choose RETRYING or FAILED based on retry count."""
        failed_stage = task.current_stage
        retry_ready_stage = PREVIOUS_READY_STAGE.get(failed_stage, failed_stage)
        task.retry_count += 1
        target = PipelineStage.RETRYING if task.retry_count <= self.max_retries else PipelineStage.FAILED
        metadata = {
            "failed_stage": failed_stage.value,
            "retry_ready_stage": retry_ready_stage.value,
        }
        if target == PipelineStage.RETRYING:
            settings = get_settings()
            delay = settings.pipeline_retry_initial_delay_seconds * (
                settings.pipeline_retry_backoff_multiplier ** max(task.retry_count - 1, 0)
            )
            metadata["next_retry_at"] = (self._now() + timedelta(seconds=delay)).isoformat()
        return self.transition(task, target, metadata=metadata, error=exc)

    def update_metadata(self, task: PipelineTask, values: dict[str, Any], commit: bool = True) -> PipelineTask:
        """Merge task metadata JSON with new values."""
        metadata = self.metadata(task)
        metadata.update(values)
        task.metadata_json = json.dumps(metadata, default=str)
        task.updated_at = self._now()
        if "video_id" in values and values["video_id"]:
            task.video_id = int(values["video_id"])
        if commit:
            self.db.commit()
            self.db.refresh(task)
        return task

    def metadata(self, task: PipelineTask) -> dict[str, Any]:
        """Return validated task metadata as a dictionary."""
        try:
            parsed = json.loads(task.metadata_json or "{}")
        except json.JSONDecodeError:
            pipeline_logger.exception("Pipeline metadata corruption task_uuid=%s", task.task_uuid)
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def task_for_topic(self, topic_id: int) -> PipelineTask | None:
        return self.db.scalars(
            select(PipelineTask)
            .where(PipelineTask.topic_id == topic_id)
            .order_by(PipelineTask.updated_at.desc())
        ).first()

    def task_for_video(self, video_id: int) -> PipelineTask | None:
        return self.db.scalars(
            select(PipelineTask)
            .where(PipelineTask.video_id == video_id)
            .order_by(PipelineTask.updated_at.desc())
        ).first()

    def adopt_script(self, script_id: int) -> PipelineTask:
        script = self.db.get(Script, script_id)
        if script is None:
            raise PipelineTaskNotFoundError(f"Script {script_id} was not found")
        task = self.task_for_topic(script.topic_id)
        if task is None:
            task = self.create_task(
                topic_id=script.topic_id,
                current_stage=PipelineStage.SCRIPT_READY,
                status=PipelineTaskStatus.READY,
                metadata={"script_id": script.id},
            )
        else:
            self.update_metadata(task, {"script_id": script.id})
        return task

    def adopt_audio(self, audio_id: int) -> PipelineTask:
        audio = self.db.get(Audio, audio_id)
        if audio is None:
            raise PipelineTaskNotFoundError(f"Audio {audio_id} was not found")
        task = self.adopt_script(audio.script_id)
        self.update_metadata(task, {"audio_id": audio.id})
        if task.current_stage in {PipelineStage.NEW, PipelineStage.RESEARCH_READY, PipelineStage.SCRIPT_READY}:
            task.current_stage = PipelineStage.AUDIO_READY
            task.status = PipelineTaskStatus.READY
            self.db.commit()
            self.db.refresh(task)
        return task

    def adopt_video(self, video_id: int) -> PipelineTask:
        video = self.db.get(Video, video_id)
        if video is None:
            raise PipelineTaskNotFoundError(f"Video {video_id} was not found")
        task = self.adopt_audio(video.audio_id)
        self.update_metadata(task, {"video_id": video.id, "audio_id": video.audio_id})
        task.video_id = video.id
        if task.current_stage in {PipelineStage.SCRIPT_READY, PipelineStage.AUDIO_READY}:
            task.current_stage = PipelineStage.VIDEO_READY
            task.status = PipelineTaskStatus.READY
            self.db.commit()
            self.db.refresh(task)
        return task

    def tasks_at_stage(self, stage: PipelineStage, limit: int | None = None) -> list[PipelineTask]:
        statement = (
            select(PipelineTask)
            .where(PipelineTask.current_stage == stage)
            .where(PipelineTask.status.in_(READY_STATUSES))
            .order_by(PipelineTask.updated_at.asc())
        )
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.db.scalars(statement))

    def ready_for_retry(self, limit: int | None = None) -> list[PipelineTask]:
        statement = (
            select(PipelineTask)
            .where(PipelineTask.current_stage.in_([PipelineStage.FAILED, PipelineStage.RETRYING]))
            .order_by(PipelineTask.updated_at.asc())
        )
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.db.scalars(statement))

    def activate_due_retries(self) -> int:
        """Move due RETRYING tasks back to the previous safe ready stage."""
        now = self._now()
        activated = 0
        for task in self.ready_for_retry():
            if task.current_stage != PipelineStage.RETRYING:
                continue
            metadata = self.metadata(task)
            next_retry_at = self._parse_datetime(metadata.get("next_retry_at"))
            if next_retry_at is not None and next_retry_at > now:
                continue
            stage_value = metadata.get("retry_ready_stage")
            try:
                ready_stage = PipelineStage(stage_value)
            except Exception:
                ready_stage = PipelineStage.NEW
            previous_stage = task.current_stage
            task.current_stage = ready_stage
            task.status = PipelineTaskStatus.RETRYING
            task.worker_id = None
            task.updated_at = now
            self.db.add(task)
            activated += 1
            self._log_transition(task, previous_stage, ready_stage, 0.0, "retry_activated", task.last_error)
        self.db.commit()
        return activated

    def recover_stale_running(self, timeout_seconds: int | None = None) -> int:
        """Mark stale running tasks interrupted and move them to the previous safe stage."""
        settings = get_settings()
        timeout = timeout_seconds if timeout_seconds is not None else settings.pipeline_stale_timeout_seconds
        cutoff = self._now() - timedelta(seconds=timeout)
        tasks = list(
            self.db.scalars(
                select(PipelineTask)
                .where(PipelineTask.status == PipelineTaskStatus.RUNNING)
                .where(PipelineTask.updated_at < cutoff)
            )
        )
        recovered = 0
        for task in tasks:
            previous = PREVIOUS_READY_STAGE.get(task.current_stage, PipelineStage.RETRYING)
            metadata = self.metadata(task)
            metadata["interrupted_stage"] = task.current_stage.value
            task.current_stage = previous
            task.status = PipelineTaskStatus.INTERRUPTED
            task.worker_id = None
            task.last_error = f"Interrupted during {metadata['interrupted_stage']}"
            task.metadata_json = json.dumps(metadata)
            task.updated_at = self._now()
            self.db.add(task)
            recovered += 1
            pipeline_logger.warning(
                "Pipeline task interrupted task_uuid=%s previous_stage=%s recovered_stage=%s worker=%s retry_count=%s",
                task.task_uuid,
                metadata["interrupted_stage"],
                previous.value,
                self.worker_id,
                task.retry_count,
            )
        self.db.commit()
        return recovered

    def resume_interrupted(self, task: PipelineTask) -> PipelineTask:
        """Convert an interrupted task back to a schedulable ready status."""
        if task.status != PipelineTaskStatus.INTERRUPTED:
            return task
        task.status = PipelineTaskStatus.RETRYING
        task.updated_at = self._now()
        self.db.commit()
        self.db.refresh(task)
        return task

    def claim(self, task: PipelineTask, running_stage: PipelineStage, expected: PipelineStage | Iterable[PipelineStage]) -> PipelineTask:
        """Move a ready task to a running stage with optimistic validation."""
        return self.transition(task, running_stage, expected=expected)

    def _status_for_stage(self, stage: PipelineStage) -> PipelineTaskStatus:
        if stage in RUNNING_STAGES:
            return PipelineTaskStatus.RUNNING
        if stage == PipelineStage.PUBLISHED:
            return PipelineTaskStatus.COMPLETED
        if stage == PipelineStage.FAILED:
            return PipelineTaskStatus.FAILED
        if stage == PipelineStage.RETRYING:
            return PipelineTaskStatus.RETRYING
        if stage == PipelineStage.CANCELLED:
            return PipelineTaskStatus.CANCELLED
        if stage == PipelineStage.NEW:
            return PipelineTaskStatus.PENDING
        return PipelineTaskStatus.READY

    def _expected_set(self, expected: PipelineStage | Iterable[PipelineStage] | None) -> set[PipelineStage]:
        if expected is None:
            return set()
        if isinstance(expected, PipelineStage):
            return {expected}
        return set(expected)

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    def _log_transition(
        self,
        task: PipelineTask,
        previous_stage: PipelineStage | None,
        next_stage: PipelineStage,
        duration: float,
        status: str,
        error: Exception | str | None,
    ) -> None:
        pipeline_logger.info(
            "Pipeline transition task_uuid=%s previous_stage=%s next_stage=%s duration=%.3fs worker=%s retry_count=%s status=%s exception=%s",
            task.task_uuid,
            previous_stage.value if previous_stage else None,
            next_stage.value,
            duration,
            self.worker_id,
            task.retry_count,
            status,
            str(error) if error else None,
        )
