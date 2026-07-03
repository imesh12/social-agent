import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from services.utils.logging import get_rotating_logger

pipeline_logger = get_rotating_logger("pipeline", "pipeline.log")


class PipelineReportService:
    """Persist live pipeline progress and final validation reports as JSON files."""

    def __init__(self, output_dir: str = "storage/generated/pipeline_reports") -> None:
        self.output_dir = Path(output_dir)

    def start_report(self) -> dict[str, Any]:
        """Create a new in-memory pipeline report and persist the initial state."""
        timestamp = datetime.now(timezone.utc).isoformat()
        run_id = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        report: dict[str, Any] = {
            "run_id": run_id,
            "timestamp": timestamp,
            "status": "running",
            "current_stage": "",
            "progress": 0,
            "runtime": 0.0,
            "stage_count": 8,
            "completed_stage_count": 0,
            "stages": [],
            "ids": {},
            "scores": {},
            "upload_status": {},
            "warnings": [],
            "errors": [],
            "_started_at": perf_counter(),
        }
        self.save_report(report)
        return report

    def start_stage(self, report: dict[str, Any], name: str) -> dict[str, Any]:
        """Record a stage as running and persist progress."""
        stage = {
            "name": name,
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "duration": None,
            "details": {},
            "error": "",
            "_started_at": perf_counter(),
        }
        report["current_stage"] = name
        report["stages"].append(stage)
        self.save_report(report)
        return stage

    def complete_stage(self, report: dict[str, Any], stage: dict[str, Any], details: dict[str, Any] | None = None) -> None:
        """Mark a stage completed and persist progress."""
        stage["status"] = "completed"
        stage["completed_at"] = datetime.now(timezone.utc).isoformat()
        stage["duration"] = round(perf_counter() - float(stage.pop("_started_at")), 3)
        stage["details"] = details or {}
        report["completed_stage_count"] += 1
        report["progress"] = self._progress(report)
        self.save_report(report)
        pipeline_logger.info("Pipeline stage completed name=%s duration=%s", stage["name"], stage["duration"])

    def fail_stage(self, report: dict[str, Any], stage: dict[str, Any], error: str) -> None:
        """Mark a stage failed and persist the error without raising."""
        stage["status"] = "failed"
        stage["completed_at"] = datetime.now(timezone.utc).isoformat()
        stage["duration"] = round(perf_counter() - float(stage.pop("_started_at")), 3)
        stage["error"] = error
        report["errors"].append({"stage": stage["name"], "error": error})
        report["completed_stage_count"] += 1
        report["progress"] = self._progress(report)
        self.save_report(report)
        pipeline_logger.exception("Pipeline stage failed name=%s error=%s", stage["name"], error)

    def skip_stage(self, report: dict[str, Any], name: str, reason: str) -> None:
        """Record a skipped stage when an upstream dependency is unavailable."""
        report["stages"].append(
            {
                "name": name,
                "status": "skipped",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "duration": 0.0,
                "details": {},
                "error": reason,
            }
        )
        report["warnings"].append({"stage": name, "warning": reason})
        report["completed_stage_count"] += 1
        report["progress"] = self._progress(report)
        self.save_report(report)

    def finalize(self, report: dict[str, Any]) -> Path:
        """Finalize and persist the report, returning the report path."""
        report["runtime"] = round(perf_counter() - float(report.pop("_started_at")), 3)
        report["status"] = "completed_with_errors" if report["errors"] else "completed"
        report["current_stage"] = ""
        report["progress"] = 100
        path = self.save_report(report)
        self._save_history_entry(report, path)
        pipeline_logger.info("Pipeline report finalized path=%s status=%s", path, report["status"])
        return path

    def save_report(self, report: dict[str, Any]) -> Path:
        """Persist the live report and return its run-specific path."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        serializable = self._public_report(report)
        path = self.output_dir / f"{serializable['run_id']}.json"
        path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")
        (self.output_dir / "latest.json").write_text(json.dumps(serializable, indent=2), encoding="utf-8")
        return path

    def collect_scores(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Extract all known evaluation scores from generation metadata."""
        return {
            "script_score": metadata.get("script_score"),
            "originality_score": metadata.get("originality_score"),
            "fact_confidence": metadata.get("overall_confidence"),
            "hook_scores": metadata.get("hook_scores", []),
            "content_intelligence": metadata.get("content_intelligence", {}),
            "thumbnail_intelligence": metadata.get("thumbnail_intelligence", {}),
            "seo_intelligence": metadata.get("seo_intelligence", {}),
            "viral_prediction": metadata.get("viral_prediction", {}),
            "publisher_decision": metadata.get("publisher_decision", {}),
        }

    def _save_history_entry(self, report: dict[str, Any], path: Path) -> None:
        index_path = self.output_dir / "index.json"
        try:
            history = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
        except Exception:
            history = []
        entry = {
            "run_id": report["run_id"],
            "timestamp": report["timestamp"],
            "status": report["status"],
            "runtime": report["runtime"],
            "progress": report["progress"],
            "errors": len(report["errors"]),
            "report_path": str(path).replace("\\", "/"),
        }
        history = [entry] + [item for item in history if item.get("run_id") != report["run_id"]]
        index_path.write_text(json.dumps(history[:20], indent=2), encoding="utf-8")

    def _progress(self, report: dict[str, Any]) -> int:
        stage_count = max(int(report.get("stage_count", 1)), 1)
        return min(99, round((int(report["completed_stage_count"]) / stage_count) * 100))

    def _public_report(self, report: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in report.items() if not key.startswith("_")}
