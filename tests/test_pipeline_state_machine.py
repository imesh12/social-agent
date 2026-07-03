from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from database.database import Base, SessionLocal, engine
from database.models import PipelineStage, PipelineTaskStatus, Script, Topic, TopicStatus
from scheduler.job_manager import JobManager
from services.pipeline_state_service import PipelineStateMachine, PipelineTransitionError


def setup_module() -> None:
    Base.metadata.create_all(bind=engine)


def test_pipeline_state_machine_valid_workflow_transition() -> None:
    db = SessionLocal()
    try:
        topic = Topic(title="State Machine Topic", score=88, status=TopicStatus.NEW)
        db.add(topic)
        db.commit()
        db.refresh(topic)

        machine = PipelineStateMachine(db)
        task = machine.create_task(topic_id=topic.id)
        machine.transition(task, PipelineStage.RESEARCHING, expected=PipelineStage.NEW)
        machine.transition(task, PipelineStage.RESEARCH_READY, expected=PipelineStage.RESEARCHING)

        assert task.current_stage == PipelineStage.RESEARCH_READY
        assert task.status == PipelineTaskStatus.READY
        assert task.worker_id is None
    finally:
        db.close()


def test_pipeline_state_machine_rejects_invalid_transition() -> None:
    db = SessionLocal()
    try:
        machine = PipelineStateMachine(db)
        task = machine.create_task()

        try:
            machine.transition(task, PipelineStage.AUDIO_READY, expected=PipelineStage.NEW)
        except PipelineTransitionError as exc:
            assert "Invalid pipeline transition" in str(exc)
        else:
            raise AssertionError("Expected invalid transition to fail")
    finally:
        db.close()


def test_pipeline_state_machine_retry_returns_to_previous_ready_stage() -> None:
    db = SessionLocal()
    try:
        machine = PipelineStateMachine(db)
        task = machine.create_task(current_stage=PipelineStage.SCRIPT_READY)
        machine.transition(task, PipelineStage.AUDIO_GENERATING, expected=PipelineStage.SCRIPT_READY)

        machine.mark_retry_or_failed(task, RuntimeError("edge tts unavailable"))
        metadata = machine.metadata(task)
        metadata["next_retry_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        machine.update_metadata(task, metadata)

        activated = machine.activate_due_retries()

        assert activated >= 1
        assert task.current_stage == PipelineStage.SCRIPT_READY
        assert task.status == PipelineTaskStatus.RETRYING
        assert task.retry_count == 1
    finally:
        db.close()


def test_pipeline_state_machine_recovers_stale_running_task() -> None:
    db = SessionLocal()
    try:
        machine = PipelineStateMachine(db)
        task = machine.create_task(current_stage=PipelineStage.AUDIO_READY)
        machine.transition(task, PipelineStage.VIDEO_GENERATING, expected=PipelineStage.AUDIO_READY)
        task.updated_at = datetime.now(timezone.utc) - timedelta(hours=3)
        db.commit()

        recovered = machine.recover_stale_running(timeout_seconds=1)

        assert recovered >= 1
        db.refresh(task)
        assert task.current_stage == PipelineStage.AUDIO_READY
        assert task.status == PipelineTaskStatus.INTERRUPTED
    finally:
        db.close()


def test_scheduler_selects_tasks_by_pipeline_state() -> None:
    db = SessionLocal()
    try:
        topic = Topic(title="Scheduler Pipeline Topic", score=91, status=TopicStatus.SCRIPTED)
        script = Script(topic=topic, content="Short script.")
        db.add(script)
        db.commit()
        db.refresh(script)

        class FakeManager:
            def __init__(self) -> None:
                self.called_with: list[int] = []

            async def generate_audio(self, script_id: int):
                self.called_with.append(script_id)
                return type("AudioResult", (), {"id": 123})()

        fake = FakeManager()

        def factory(_db):
            return fake

        manager = JobManager(db=db, manager_factory=factory, daily_video_count=1)
        created = db.scalars(select(Script).where(Script.id == script.id)).first()
        assert created is not None

        manager._prepare_pipeline_tasks()
        tasks = manager.pipeline_state.tasks_at_stage(PipelineStage.SCRIPT_READY)

        assert any(manager.pipeline_state.metadata(task).get("script_id") == script.id for task in tasks)
    finally:
        db.close()
