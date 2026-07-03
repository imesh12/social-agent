import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from database.database import SessionLocal
from database.models import PublishJobStatus
from scheduler.job_manager import JobManager
from services.pipeline_report_service import PipelineReportService


class FakePipelineManager:
    def __init__(self, fail_stage: str | None = None) -> None:
        self.fail_stage = fail_stage

    def generate_script(self) -> SimpleNamespace:
        if self.fail_stage == "script":
            raise RuntimeError("script failed")
        return SimpleNamespace(id=101)

    async def generate_audio(self, script_id: int) -> SimpleNamespace:
        if self.fail_stage == "audio":
            raise RuntimeError("audio failed")
        return SimpleNamespace(id=102)

    def generate_video(self, audio_id: int) -> SimpleNamespace:
        if self.fail_stage == "video":
            raise RuntimeError("video failed")
        return SimpleNamespace(id=103, path="storage/videos/fake_pipeline.mp4")

    def generate_subtitles(self, video_id: int) -> SimpleNamespace:
        return SimpleNamespace(id=104, path="storage/subtitles/fake_pipeline.srt")

    def generate_seo(self, video_id: int) -> SimpleNamespace:
        return SimpleNamespace(id=105, title="SEO title")

    def generate_thumbnail(self, video_id: int) -> SimpleNamespace:
        return SimpleNamespace(id=106, path="storage/thumbnails/fake_pipeline.jpg")

    def publish_youtube(self, video_id: int) -> SimpleNamespace:
        return SimpleNamespace(
            id=107,
            youtube_video_id="youtube-pipeline-id",
            youtube_url="https://www.youtube.com/watch?v=youtube-pipeline-id",
            status=PublishJobStatus.UPLOADED,
        )


def test_pipeline_report_service_persists_report_and_history(tmp_path: Path) -> None:
    service = PipelineReportService(output_dir=str(tmp_path))
    report = service.start_report()
    stage = service.start_stage(report, "script")
    service.complete_stage(report, stage, {"id": 1})
    path = service.finalize(report)

    saved = json.loads(path.read_text(encoding="utf-8"))
    history = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert saved["status"] == "completed"
    assert saved["progress"] == 100
    assert saved["stages"][0]["duration"] >= 0
    assert history[0]["run_id"] == saved["run_id"]


def test_run_full_pipeline_creates_complete_report() -> None:
    db = SessionLocal()
    try:
        manager = JobManager(db=db, manager_factory=lambda session: FakePipelineManager())
        result = asyncio.run(manager.run_full_pipeline())

        report_path = Path(result["report_path"])
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert result["status"] == "completed"
        assert result["script_id"] == 101
        assert report["status"] == "completed"
        assert report["progress"] == 100
        assert [stage["name"] for stage in report["stages"]] == [
            "script",
            "audio",
            "video",
            "subtitles",
            "seo",
            "thumbnail",
            "publish",
            "metadata",
        ]
        assert all(stage["duration"] is not None for stage in report["stages"])
    finally:
        db.close()


def test_run_full_pipeline_records_stage_failure_without_crashing() -> None:
    db = SessionLocal()
    try:
        manager = JobManager(db=db, manager_factory=lambda session: FakePipelineManager(fail_stage="audio"))
        result = asyncio.run(manager.run_full_pipeline())

        report = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
        assert result["status"] == "completed_with_errors"
        assert result["audio_id"] == 0
        assert report["status"] == "completed_with_errors"
        assert any(error["stage"] == "audio" for error in report["errors"])
        assert any(stage["status"] == "skipped" for stage in report["stages"])
    finally:
        db.close()


def test_pipeline_report_collects_ai_scores() -> None:
    service = PipelineReportService()
    scores = service.collect_scores(
        {
            "script_score": {"overall": 91},
            "originality_score": 88,
            "overall_confidence": 84,
            "hook_scores": [{"overall_score": 90}],
            "content_intelligence": {"overall_retention_score": 89},
            "thumbnail_intelligence": {"overall_score": 87},
            "seo_intelligence": {"overall_score": 86},
            "viral_prediction": {"viral_score": 85},
            "publisher_decision": {"overall_score": 90},
        }
    )

    assert scores["script_score"]["overall"] == 91
    assert scores["originality_score"] == 88
    assert scores["viral_prediction"]["viral_score"] == 85


def test_dashboard_contains_pipeline_history_bindings() -> None:
    html = Path("frontend/index.html").read_text(encoding="utf-8")
    javascript = Path("frontend/app.js").read_text(encoding="utf-8")

    assert "Run Complete Pipeline" in html
    assert "Pipeline Progress" in html
    assert "Pipeline History" in html
    assert "pipelineProgress" in html
    assert "pipelineHistoryOutput" in html
    assert "pipeline_reports/latest.json" in javascript
    assert "pipeline_reports/index.json" in javascript
