import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from database.models import SEO, Thumbnail, Video
from services.competitor_analysis_service import CompetitorAnalysis
from services.content_intelligence_service import AudienceRetentionAnalysis
from services.fact_verification_service import FactVerificationResult
from services.hook_intelligence_service import HookSelection
from services.llm.base_llm_service import ScriptScore
from services.publisher_decision_service import PublisherDecisionResult
from services.seo_intelligence_service import SEOIntelligenceResult
from services.thumbnail_intelligence_service import ThumbnailIntelligenceResult
from services.utils.logging import get_rotating_logger
from services.viral_prediction_service import ViralPredictionResult
from services.version_selection_service import VersionSelectionResult
from services.youtube_service import YouTubeUploadResult

metadata_logger = get_rotating_logger("system_health", "system_health.log")


class GenerationMetadataService:
    """Persist generation history as timestamped JSON files."""

    def __init__(self, output_dir: str = "storage/generated") -> None:
        self.output_dir = Path(output_dir)

    def save_metadata(self, metadata: dict[str, Any]) -> Path:
        """Save metadata to a timestamped JSON file and return the path."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        path = self.output_dir / f"{timestamp}.json"
        suffix = 1
        while path.exists():
            path = self.output_dir / f"{timestamp}_{suffix}.json"
            suffix += 1
        path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        (self.output_dir / "latest.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return path

    def save_script_quality(
        self,
        script_id: int,
        score: ScriptScore | None,
        accepted: bool,
        regenerated: bool,
        attempt_count: int,
    ) -> Path | None:
        """Persist script quality metadata without changing the database."""
        try:
            payload: dict[str, Any] = {
                "script_id": script_id,
                "script_score": score.score_summary() if score else None,
                "accepted": accepted,
                "regenerated": regenerated,
                "attempt_count": attempt_count,
            }
            score_dir = self.output_dir / "script_scores"
            score_dir.mkdir(parents=True, exist_ok=True)
            path = score_dir / f"script_{script_id}.json"
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return path
        except Exception as exc:
            metadata_logger.exception("Script quality metadata saving failure script_id=%s error=%s", script_id, exc)
            return None

    def load_script_quality(self, script_id: int) -> dict[str, Any]:
        """Load persisted script quality metadata for generation history."""
        path = self.output_dir / "script_scores" / f"script_{script_id}.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            metadata_logger.exception("Script quality metadata load failure script_id=%s error=%s", script_id, exc)
            return {}

    def save_script_variants(
        self,
        script_id: int,
        selection: VersionSelectionResult | None,
    ) -> Path | None:
        """Persist creative version metadata without changing the database."""
        if selection is None:
            return None
        try:
            payload: dict[str, Any] = {
                "script_id": script_id,
                "script_variants": {
                    "winner": selection.winner,
                    "version_scores": selection.scores,
                    "selection_reason": selection.reason,
                    "version_count": len(selection.evaluations),
                    "best_hook": selection.best_hook,
                    "versions": [
                        {
                            "label": item.label,
                            "focus": item.focus,
                            "reviewed_script": item.reviewed_script,
                            "overall_score": item.overall_score,
                            "script_score": item.script_score.score_summary(),
                            "retention_score": item.content_intelligence.overall_retention_score,
                        }
                        for item in selection.evaluations
                    ],
                },
            }
            output_dir = self.output_dir / "script_variants"
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / f"script_{script_id}.json"
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return path
        except Exception as exc:
            metadata_logger.exception("Script variants saving failure script_id=%s error=%s", script_id, exc)
            return None

    def load_script_variants(self, script_id: int) -> dict[str, Any]:
        """Load creative version metadata for generation history."""
        path = self.output_dir / "script_variants" / f"script_{script_id}.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("script_variants", {})
        except Exception as exc:
            metadata_logger.exception("Script variants load failure script_id=%s error=%s", script_id, exc)
            return {}

    def save_research_intelligence(
        self,
        script_id: int,
        competitor_analysis: CompetitorAnalysis | None,
    ) -> Path | None:
        """Persist research intelligence metadata without changing the database."""
        if competitor_analysis is None:
            return None
        try:
            payload: dict[str, Any] = {
                "script_id": script_id,
                "originality_score": competitor_analysis.originality_score,
                "chosen_video_angle": competitor_analysis.unique_video_angle,
                "competitor_titles": competitor_analysis.competitor_titles,
                "missing_angles": competitor_analysis.missing_angles,
                "competitors_analyzed": len(competitor_analysis.competitor_titles),
            }
            research_dir = self.output_dir / "research_intelligence"
            research_dir.mkdir(parents=True, exist_ok=True)
            path = research_dir / f"script_{script_id}.json"
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return path
        except Exception as exc:
            metadata_logger.exception("Research intelligence saving failure script_id=%s error=%s", script_id, exc)
            return None

    def load_research_intelligence(self, script_id: int) -> dict[str, Any]:
        """Load persisted research intelligence metadata for generation history."""
        path = self.output_dir / "research_intelligence" / f"script_{script_id}.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            metadata_logger.exception("Research intelligence load failure script_id=%s error=%s", script_id, exc)
            return {}

    def save_fact_verification(
        self,
        script_id: int,
        fact_verification: FactVerificationResult | None,
    ) -> Path | None:
        """Persist fact verification metadata without changing the database."""
        if fact_verification is None:
            return None
        try:
            payload: dict[str, Any] = {
                "script_id": script_id,
                "overall_confidence": fact_verification.overall_confidence,
                "verified_claims": fact_verification.verified_claims,
                "rejected_claims": fact_verification.rejected_claims,
                "verification_sources": fact_verification.sources_checked,
                "verification_time": fact_verification.verification_time,
                "fallback_used": fact_verification.fallback_used,
            }
            verification_dir = self.output_dir / "fact_verification"
            verification_dir.mkdir(parents=True, exist_ok=True)
            path = verification_dir / f"script_{script_id}.json"
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return path
        except Exception as exc:
            metadata_logger.exception("Fact verification saving failure script_id=%s error=%s", script_id, exc)
            return None

    def load_fact_verification(self, script_id: int) -> dict[str, Any]:
        """Load persisted fact verification metadata for generation history."""
        path = self.output_dir / "fact_verification" / f"script_{script_id}.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            metadata_logger.exception("Fact verification load failure script_id=%s error=%s", script_id, exc)
            return {}

    def save_hook_intelligence(
        self,
        script_id: int,
        hook_selection: HookSelection | None,
    ) -> Path | None:
        """Persist hook intelligence metadata without changing the database."""
        if hook_selection is None:
            return None
        try:
            payload: dict[str, Any] = {
                "script_id": script_id,
                "selected_hook": hook_selection.selected_hook.text,
                "top_hooks": [hook.text for hook in hook_selection.top_hooks],
                "hook_scores": [
                    {
                        "text": hook.text,
                        "type": hook.type,
                        "emotion": hook.emotion,
                        "curiosity_score": hook.curiosity_score,
                        "clarity_score": hook.clarity_score,
                        "novelty_score": hook.novelty_score,
                        "retention_score": hook.retention_score,
                        "overall_score": hook.overall_score,
                    }
                    for hook in hook_selection.top_hooks
                ],
                "hook_type": hook_selection.selected_hook.type,
                "selection_reason": hook_selection.selection_reason,
            }
            hook_dir = self.output_dir / "hook_intelligence"
            hook_dir.mkdir(parents=True, exist_ok=True)
            path = hook_dir / f"script_{script_id}.json"
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return path
        except Exception as exc:
            metadata_logger.exception("Hook intelligence saving failure script_id=%s error=%s", script_id, exc)
            return None

    def load_hook_intelligence(self, script_id: int) -> dict[str, Any]:
        """Load persisted hook intelligence metadata for generation history."""
        path = self.output_dir / "hook_intelligence" / f"script_{script_id}.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            metadata_logger.exception("Hook intelligence load failure script_id=%s error=%s", script_id, exc)
            return {}

    def save_content_intelligence(
        self,
        script_id: int,
        analysis: AudienceRetentionAnalysis | None,
    ) -> Path | None:
        """Persist content intelligence metadata without changing the database."""
        if analysis is None:
            return None
        try:
            payload: dict[str, Any] = {
                "script_id": script_id,
                "content_intelligence": {
                    **analysis.score_summary(),
                    "predicted_drop_points": analysis.predicted_drop_points,
                    "improvements": analysis.improvements,
                    "strengths": analysis.strengths,
                    "analysis_timestamp": analysis.analysis_timestamp,
                    "fallback_used": analysis.fallback_used,
                },
            }
            output_dir = self.output_dir / "content_intelligence"
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / f"script_{script_id}.json"
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return path
        except Exception as exc:
            metadata_logger.exception("Content intelligence saving failure script_id=%s error=%s", script_id, exc)
            return None

    def load_content_intelligence(self, script_id: int) -> dict[str, Any]:
        """Load persisted content intelligence metadata for generation history."""
        path = self.output_dir / "content_intelligence" / f"script_{script_id}.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("content_intelligence", {})
        except Exception as exc:
            metadata_logger.exception("Content intelligence load failure script_id=%s error=%s", script_id, exc)
            return {}

    def save_thumbnail_intelligence(
        self,
        video_id: int,
        result: ThumbnailIntelligenceResult | None,
    ) -> Path | None:
        """Persist thumbnail intelligence metadata without changing the database."""
        if result is None:
            return None
        try:
            payload: dict[str, Any] = {
                "video_id": video_id,
                "thumbnail_intelligence": result.score_summary(),
            }
            output_dir = self.output_dir / "thumbnail_intelligence"
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / f"video_{video_id}.json"
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return path
        except Exception as exc:
            metadata_logger.exception("Thumbnail intelligence saving failure video_id=%s error=%s", video_id, exc)
            return None

    def load_thumbnail_intelligence(self, video_id: int) -> dict[str, Any]:
        """Load persisted thumbnail intelligence metadata for generation history."""
        path = self.output_dir / "thumbnail_intelligence" / f"video_{video_id}.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("thumbnail_intelligence", {})
        except Exception as exc:
            metadata_logger.exception("Thumbnail intelligence load failure video_id=%s error=%s", video_id, exc)
            return {}

    def save_seo_intelligence(
        self,
        video_id: int,
        result: SEOIntelligenceResult | None,
    ) -> Path | None:
        """Persist SEO intelligence metadata without changing the database."""
        if result is None:
            return None
        try:
            payload: dict[str, Any] = {
                "video_id": video_id,
                "seo_intelligence": result.score_summary(),
            }
            output_dir = self.output_dir / "seo_intelligence"
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / f"video_{video_id}.json"
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return path
        except Exception as exc:
            metadata_logger.exception("SEO intelligence saving failure video_id=%s error=%s", video_id, exc)
            return None

    def load_seo_intelligence(self, video_id: int) -> dict[str, Any]:
        """Load persisted SEO intelligence metadata for generation history."""
        path = self.output_dir / "seo_intelligence" / f"video_{video_id}.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("seo_intelligence", {})
        except Exception as exc:
            metadata_logger.exception("SEO intelligence load failure video_id=%s error=%s", video_id, exc)
            return {}

    def save_viral_prediction(
        self,
        video_id: int,
        result: ViralPredictionResult | None,
    ) -> Path | None:
        """Persist viral prediction metadata without changing the database."""
        if result is None:
            return None
        try:
            payload: dict[str, Any] = {
                "video_id": video_id,
                "viral_prediction": result.model_dump(),
            }
            output_dir = self.output_dir / "viral_prediction"
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / f"video_{video_id}.json"
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return path
        except Exception as exc:
            metadata_logger.exception("Viral prediction saving failure video_id=%s error=%s", video_id, exc)
            return None

    def load_viral_prediction(self, video_id: int) -> dict[str, Any]:
        """Load persisted viral prediction metadata for generation history."""
        path = self.output_dir / "viral_prediction" / f"video_{video_id}.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("viral_prediction", {})
        except Exception as exc:
            metadata_logger.exception("Viral prediction load failure video_id=%s error=%s", video_id, exc)
            return {}

    def save_publisher_decision(
        self,
        video_id: int,
        result: PublisherDecisionResult | None,
    ) -> Path | None:
        """Persist publisher decision metadata without changing the database."""
        if result is None:
            return None
        try:
            payload: dict[str, Any] = {
                "video_id": video_id,
                "publisher_decision": result.model_dump(),
            }
            output_dir = self.output_dir / "publisher_decision"
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / f"video_{video_id}.json"
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return path
        except Exception as exc:
            metadata_logger.exception("Publisher decision saving failure video_id=%s error=%s", video_id, exc)
            return None

    def load_publisher_decision(self, video_id: int) -> dict[str, Any]:
        """Load persisted publisher decision metadata for generation history."""
        path = self.output_dir / "publisher_decision" / f"video_{video_id}.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("publisher_decision", {})
        except Exception as exc:
            metadata_logger.exception("Publisher decision load failure video_id=%s error=%s", video_id, exc)
            return {}

    def save_youtube_upload(self, video_id: int, result: YouTubeUploadResult) -> Path | None:
        """Persist YouTube upload metadata without changing the database."""
        try:
            payload: dict[str, Any] = {
                "video_id": video_id,
                "youtube_upload": {
                    "upload_status": "uploaded",
                    "progress": result.progress,
                    "video_id": result.youtube_video_id,
                    "video_url": result.youtube_url,
                    "thumbnail_url": result.thumbnail_url,
                    "published_at": result.published_at,
                    "upload_time": result.upload_time,
                    "processing_status": result.processing_status,
                    "error": result.error,
                },
            }
            output_dir = self.output_dir / "youtube_uploads"
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / f"video_{video_id}.json"
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return path
        except Exception as exc:
            metadata_logger.exception("YouTube upload metadata saving failure video_id=%s error=%s", video_id, exc)
            return None

    def save_youtube_upload_error(self, video_id: int, error: str) -> Path | None:
        """Persist a failed YouTube upload attempt without changing the database."""
        try:
            payload: dict[str, Any] = {
                "video_id": video_id,
                "youtube_upload": {
                    "upload_status": "failed",
                    "progress": 0,
                    "video_id": "",
                    "video_url": "",
                    "thumbnail_url": "",
                    "published_at": "",
                    "upload_time": 0.0,
                    "processing_status": "failed",
                    "error": error,
                },
            }
            output_dir = self.output_dir / "youtube_uploads"
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / f"video_{video_id}.json"
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return path
        except Exception as exc:
            metadata_logger.exception("YouTube upload error metadata saving failure video_id=%s error=%s", video_id, exc)
            return None

    def load_youtube_upload(self, video_id: int) -> dict[str, Any]:
        """Load persisted YouTube upload metadata for generation history."""
        path = self.output_dir / "youtube_uploads" / f"video_{video_id}.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("youtube_upload", {})
        except Exception as exc:
            metadata_logger.exception("YouTube upload metadata load failure video_id=%s error=%s", video_id, exc)
            return {}

    def save_for_video(self, db: Session, video_id: int, youtube_id: str | None = None) -> Path | None:
        """Build and save generation metadata for a video, logging failures."""
        try:
            video = db.get(Video, video_id)
            if video is None:
                raise ValueError(f"Video {video_id} was not found")

            script = video.audio.script
            seo = (
                db.query(SEO)
                .filter(SEO.video_id == video.id)
                .order_by(SEO.created_at.desc())
                .first()
            )
            thumbnail = (
                db.query(Thumbnail)
                .filter(Thumbnail.video_id == video.id)
                .order_by(Thumbnail.created_at.desc())
                .first()
            )
            script_quality = self.load_script_quality(script.id)
            script_variants = self.load_script_variants(script.id)
            research_intelligence = self.load_research_intelligence(script.id)
            fact_verification = self.load_fact_verification(script.id)
            hook_intelligence = self.load_hook_intelligence(script.id)
            content_intelligence = self.load_content_intelligence(script.id)
            thumbnail_intelligence = self.load_thumbnail_intelligence(video.id)
            seo_intelligence = self.load_seo_intelligence(video.id)
            viral_prediction = self.load_viral_prediction(video.id)
            publisher_decision = self.load_publisher_decision(video.id)
            youtube_upload = self.load_youtube_upload(video.id)
            metadata = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "topic": script.topic.title,
                "research": "",
                "script": script.content,
                "title": seo.title if seo else "",
                "description": seo.description if seo else "",
                "tags": json.loads(seo.tags) if seo else [],
                "thumbnail_path": thumbnail.path if thumbnail else "",
                "video_path": video.path,
                "youtube_id": youtube_id or "",
                "youtube_upload": youtube_upload,
                "upload_status": youtube_upload.get("upload_status"),
                "upload_progress": youtube_upload.get("progress"),
                "youtube_url": youtube_upload.get("video_url", ""),
                "youtube_thumbnail_url": youtube_upload.get("thumbnail_url", ""),
                "youtube_published_at": youtube_upload.get("published_at", ""),
                "youtube_upload_time": youtube_upload.get("upload_time"),
                "youtube_processing_status": youtube_upload.get("processing_status", ""),
                "script_score": script_quality.get("script_score"),
                "script_accepted": script_quality.get("accepted"),
                "script_regenerated": script_quality.get("regenerated"),
                "script_attempt_count": script_quality.get("attempt_count"),
                "script_variants": script_variants,
                "originality_score": research_intelligence.get("originality_score"),
                "chosen_video_angle": research_intelligence.get("chosen_video_angle", ""),
                "competitor_titles": research_intelligence.get("competitor_titles", []),
                "missing_angles": research_intelligence.get("missing_angles", []),
                "competitors_analyzed": research_intelligence.get("competitors_analyzed"),
                "overall_confidence": fact_verification.get("overall_confidence"),
                "verified_claims": fact_verification.get("verified_claims", []),
                "rejected_claims": fact_verification.get("rejected_claims", []),
                "verification_sources": fact_verification.get("verification_sources", []),
                "verification_time": fact_verification.get("verification_time"),
                "verification_fallback_used": fact_verification.get("fallback_used"),
                "selected_hook": hook_intelligence.get("selected_hook", ""),
                "top_hooks": hook_intelligence.get("top_hooks", []),
                "hook_scores": hook_intelligence.get("hook_scores", []),
                "hook_type": hook_intelligence.get("hook_type", ""),
                "hook_selection_reason": hook_intelligence.get("selection_reason", ""),
                "content_intelligence": content_intelligence,
                "thumbnail_intelligence": thumbnail_intelligence,
                "seo_intelligence": seo_intelligence,
                "viral_prediction": viral_prediction,
                "publisher_decision": publisher_decision,
            }
            path = self.save_metadata(metadata)
            metadata_logger.info("Saved generation metadata path=%s video_id=%s", path, video_id)
            return path
        except Exception as exc:
            metadata_logger.exception("Metadata saving failure video_id=%s error=%s", video_id, exc)
            return None
