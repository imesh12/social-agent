from fastapi.testclient import TestClient

from backend.main import app, get_job_manager
from scheduler.daily_scheduler import create_daily_scheduler


class FakeJobManager:
    async def run_full_pipeline(self) -> dict[str, int | str]:
        return {
            "status": "completed",
            "script_id": 1,
            "audio_id": 1,
            "video_id": 1,
            "subtitle_id": 1,
        }

    async def run_daily_jobs(self) -> dict[str, int | str]:
        return {
            "status": "completed",
            "scripts_created": 3,
            "audio_created": 3,
            "videos_created": 3,
            "subtitles_created": 3,
            "seo_created": 3,
            "thumbnails_created": 3,
        }

    def scheduler_status(self) -> dict[str, int | str | None]:
        return {
            "last_job_type": "run_daily_jobs",
            "last_job_status": "completed",
            "scheduled_job_count": 2,
        }


def override_job_manager() -> FakeJobManager:
    return FakeJobManager()


def test_run_full_pipeline_endpoint() -> None:
    app.dependency_overrides[get_job_manager] = override_job_manager
    try:
        with TestClient(app) as client:
            response = client.post("/run-full-pipeline")

        assert response.status_code == 200
        assert response.json()["status"] == "completed"
        assert response.json()["video_id"] == 1
    finally:
        app.dependency_overrides.clear()


def test_run_daily_jobs_endpoint() -> None:
    app.dependency_overrides[get_job_manager] = override_job_manager
    try:
        with TestClient(app) as client:
            response = client.post("/run-daily-jobs")

        assert response.status_code == 200
        assert response.json() == {
            "status": "completed",
            "scripts_created": 3,
            "audio_created": 3,
            "videos_created": 3,
            "subtitles_created": 3,
            "seo_created": 3,
            "thumbnails_created": 3,
        }
    finally:
        app.dependency_overrides.clear()


def test_scheduler_status_endpoint() -> None:
    app.dependency_overrides[get_job_manager] = override_job_manager
    try:
        with TestClient(app) as client:
            response = client.get("/scheduler-status")

        assert response.status_code == 200
        payload = response.json()
        assert payload["running"] is True
        assert len(payload["jobs"]) == 10
        assert payload["database"]["last_job_status"] == "completed"
    finally:
        app.dependency_overrides.clear()


def test_daily_scheduler_registers_expected_jobs() -> None:
    scheduler = create_daily_scheduler()
    jobs = {job.id: str(job.trigger) for job in scheduler.get_jobs()}

    assert set(jobs) == {
        "cleanup_storage",
        "generate_scripts",
        "generate_audio",
        "generate_videos",
        "generate_subtitles",
        "generate_seo",
        "generate_thumbnails",
        "publish_video_1",
        "publish_video_2",
        "publish_video_3",
    }
    assert "hour='2', minute='0'" in jobs["cleanup_storage"]
    assert "hour='6', minute='0'" in jobs["generate_scripts"]
    assert "hour='6', minute='10'" in jobs["generate_audio"]
    assert "hour='6', minute='20'" in jobs["generate_videos"]
    assert "hour='6', minute='25'" in jobs["generate_subtitles"]
    assert "hour='6', minute='30'" in jobs["generate_seo"]
    assert "hour='6', minute='35'" in jobs["generate_thumbnails"]
    assert "hour='12', minute='0'" in jobs["publish_video_1"]
    assert "hour='18', minute='0'" in jobs["publish_video_2"]
    assert "hour='21', minute='0'" in jobs["publish_video_3"]
