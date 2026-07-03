import json
from pathlib import Path

from services.competitor_analysis_service import CompetitorAnalysis
from services.content_intelligence_service import AudienceRetentionAnalysis
from services.fact_verification_service import ClaimVerificationDetail, FactVerificationResult
from services.hook_intelligence_service import HookCandidate, HookSelection
from services.llm.base_llm_service import ScriptScore
from services.metadata_service import GenerationMetadataService
from services.publisher_decision_service import PublisherDecisionResult
from services.seo_intelligence_service import SEOIntelligenceResult
from services.thumbnail_intelligence_service import ThumbnailIntelligenceResult
from services.viral_prediction_service import ViralPredictionResult
from services.version_selection_service import ScriptVersionEvaluation, VersionSelectionResult
from services.youtube_service import YouTubeUploadResult


def test_metadata_json_saved_correctly(tmp_path: Path) -> None:
    service = GenerationMetadataService(output_dir=str(tmp_path))
    metadata = {
        "timestamp": "2026-06-19T00:00:00+00:00",
        "topic": "AI Tools",
        "research": "AI tools are trending.",
        "script": "Hook: AI tools are changing fast.",
        "title": "Top 3 AI Tools You Need In 2026 #shorts",
        "description": "Discover AI tools changing productivity.",
        "tags": ["AI", "ChatGPT", "Technology"],
        "thumbnail_path": "storage/thumbnails/thumb_1.jpg",
        "video_path": "storage/videos/video_1.mp4",
        "youtube_id": "abc123",
    }

    path = service.save_metadata(metadata)

    assert path.exists()
    assert path.name.endswith(".json")
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == metadata


def test_script_quality_metadata_saved_correctly(tmp_path: Path) -> None:
    service = GenerationMetadataService(output_dir=str(tmp_path))
    score = ScriptScore(
        hook=93,
        clarity=91,
        retention=92,
        storytelling=90,
        cta=86,
        overall=91,
        strengths=["Strong hook"],
        improvements=["Sharper CTA"],
    )

    path = service.save_script_quality(
        script_id=7,
        score=score,
        accepted=True,
        regenerated=True,
        attempt_count=2,
    )

    assert path is not None
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["script_score"] == {
        "hook": 93,
        "clarity": 91,
        "retention": 92,
        "storytelling": 90,
        "cta": 86,
        "overall": 91,
    }
    assert service.load_script_quality(7)["attempt_count"] == 2


def test_research_intelligence_metadata_saved_correctly(tmp_path: Path) -> None:
    service = GenerationMetadataService(output_dir=str(tmp_path))
    analysis = CompetitorAnalysis(
        searched_topic="AI Tools",
        competitor_titles=["Top AI tools for creators", "Best AI apps"],
        common_angles=["tool list or roundup"],
        repeated_keywords=["ai", "tools"],
        missing_angles=["Show one practical workflow."],
        unique_video_angle="Show the AI workflow competitors skip.",
        hook_opportunities=["Most AI tool videos miss this workflow."],
        credibility_notes=["Verify claims."],
        originality_score=92,
    )

    path = service.save_research_intelligence(script_id=8, competitor_analysis=analysis)

    assert path is not None
    saved = service.load_research_intelligence(8)
    assert saved["originality_score"] == 92
    assert saved["chosen_video_angle"] == "Show the AI workflow competitors skip."
    assert saved["competitor_titles"] == ["Top AI tools for creators", "Best AI apps"]
    assert saved["missing_angles"] == ["Show one practical workflow."]
    assert saved["competitors_analyzed"] == 2


def test_fact_verification_metadata_saved_correctly(tmp_path: Path) -> None:
    service = GenerationMetadataService(output_dir=str(tmp_path))
    verification = FactVerificationResult(
        verified_claims=["AI tools help creators move faster."],
        rejected_claims=["AI tools guarantee success."],
        verification_summary="One verified, one rejected.",
        overall_confidence=84,
        sources_checked=["OpenAI"],
        verification_time=0.25,
        fallback_used=False,
        claim_details=[
            ClaimVerificationDetail(
                claim="AI tools help creators move faster.",
                status="verified",
                confidence=90,
                source="OpenAI",
                notes="Matched source.",
            )
        ],
    )

    path = service.save_fact_verification(script_id=9, fact_verification=verification)

    assert path is not None
    saved = service.load_fact_verification(9)
    assert saved["overall_confidence"] == 84
    assert saved["verified_claims"] == ["AI tools help creators move faster."]
    assert saved["rejected_claims"] == ["AI tools guarantee success."]
    assert saved["verification_sources"] == ["OpenAI"]
    assert saved["verification_time"] == 0.25
    assert saved["fallback_used"] is False


def test_hook_intelligence_metadata_saved_correctly(tmp_path: Path) -> None:
    service = GenerationMetadataService(output_dir=str(tmp_path))
    hooks = [
        HookCandidate(
            text="Most people miss the practical side of AI tools.",
            type="Curiosity",
            emotion="intrigue",
            curiosity_score=90,
            clarity_score=88,
            novelty_score=86,
            retention_score=91,
            overall_score=89,
            reasoning="Strong curiosity.",
        ),
        HookCandidate(
            text="Stop watching generic AI tools lists for a second.",
            type="Contrarian",
            emotion="skepticism",
            curiosity_score=88,
            clarity_score=84,
            novelty_score=85,
            retention_score=90,
            overall_score=87,
            reasoning="Contrarian angle.",
        ),
        HookCandidate(
            text="What if AI tools are useful for one skipped reason?",
            type="Question",
            emotion="curiosity",
            curiosity_score=86,
            clarity_score=86,
            novelty_score=84,
            retention_score=87,
            overall_score=86,
            reasoning="Question hook.",
        ),
    ]
    selection = HookSelection(
        candidates=hooks,
        selected_hook=hooks[0],
        selection_reason="Highest score.",
        generation_time=0.01,
        fallback_used=False,
    )

    path = service.save_hook_intelligence(script_id=10, hook_selection=selection)

    assert path is not None
    saved = service.load_hook_intelligence(10)
    assert saved["selected_hook"] == "Most people miss the practical side of AI tools."
    assert saved["hook_type"] == "Curiosity"
    assert saved["top_hooks"] == [hook.text for hook in hooks]
    assert saved["hook_scores"][0]["overall_score"] == 89
    assert saved["selection_reason"] == "Highest score."


def test_content_intelligence_metadata_saved_correctly(tmp_path: Path) -> None:
    service = GenerationMetadataService(output_dir=str(tmp_path))
    analysis = AudienceRetentionAnalysis(
        overall_retention_score=91,
        opening_strength=92,
        first_5_seconds=90,
        curiosity_gap=89,
        story_flow=88,
        information_density=85,
        pace=90,
        emotional_trigger=84,
        ending_strength=87,
        drop_risk="low",
        predicted_drop_points=["sentence 4"],
        improvements=["add pattern interrupt", "stronger CTA"],
        strengths=["strong hook"],
        analysis_timestamp="2026-06-30T00:00:00+00:00",
        fallback_used=False,
    )

    path = service.save_content_intelligence(script_id=11, analysis=analysis)

    assert path is not None
    saved = service.load_content_intelligence(11)
    assert saved["overall_retention_score"] == 91
    assert saved["opening_strength"] == 92
    assert saved["predicted_drop_points"] == ["sentence 4"]
    assert saved["improvements"] == ["add pattern interrupt", "stronger CTA"]
    assert saved["analysis_timestamp"] == "2026-06-30T00:00:00+00:00"


def test_thumbnail_intelligence_metadata_saved_correctly(tmp_path: Path) -> None:
    service = GenerationMetadataService(output_dir=str(tmp_path))
    result = ThumbnailIntelligenceResult(
        overall_score=91,
        ctr_prediction=90,
        curiosity_score=89,
        emotion_score=88,
        contrast_score=92,
        visual_clarity=91,
        mobile_visibility=90,
        text_readability=93,
        subject_focus=87,
        brand_consistency=84,
        recommended_changes=["use four words or fewer", "increase subject focus"],
        strengths=["clear text"],
        weaknesses=["subject could be stronger"],
        regeneration_attempt=1,
        accepted=True,
        selected_thumbnail_path="storage/thumbnails/thumb_1.jpg",
        analysis_timestamp="2026-06-30T00:00:00+00:00",
        fallback_used=False,
    )

    path = service.save_thumbnail_intelligence(video_id=12, result=result)

    assert path is not None
    saved = service.load_thumbnail_intelligence(12)
    assert saved["overall_score"] == 91
    assert saved["ctr_prediction"] == 90
    assert saved["regeneration_attempt"] == 1
    assert saved["accepted"] is True
    assert saved["selected_thumbnail_path"] == "storage/thumbnails/thumb_1.jpg"


def test_seo_intelligence_metadata_saved_correctly(tmp_path: Path) -> None:
    service = GenerationMetadataService(output_dir=str(tmp_path))
    result = SEOIntelligenceResult(
        overall_score=91,
        title_score=90,
        description_score=89,
        keyword_score=88,
        tag_score=87,
        hashtag_score=86,
        search_intent_score=91,
        ctr_prediction=90,
        competition_level="medium",
        readability_score=92,
        engagement_score=85,
        recommended_title="Better AI Tools Title #shorts",
        recommended_description="Better description.",
        recommended_tags=["AI", "Tools"],
        recommended_hashtags="#ai #shorts",
        strengths=["clear"],
        weaknesses=["none"],
        recommended_changes=["tighten title"],
        accepted=True,
        attempt=1,
        analysis_timestamp="2026-06-30T00:00:00+00:00",
        fallback_used=False,
    )

    path = service.save_seo_intelligence(video_id=13, result=result)

    assert path is not None
    saved = service.load_seo_intelligence(13)
    assert saved["overall_score"] == 91
    assert saved["title_score"] == 90
    assert saved["recommended_title"] == "Better AI Tools Title #shorts"
    assert saved["attempt"] == 1
    assert saved["accepted"] is True


def test_viral_prediction_metadata_saved_correctly(tmp_path: Path) -> None:
    service = GenerationMetadataService(output_dir=str(tmp_path))
    result = ViralPredictionResult(
        viral_score=91,
        predicted_ctr=88,
        predicted_retention=89,
        shareability="High",
        uniqueness="High",
        competition="Medium",
        emotion="curiosity",
        risk_level="Low",
        confidence=86,
        publish_recommendation=True,
        reasons=["strong hook"],
        improvements=["increase emotional contrast"],
        analysis_timestamp="2026-06-30T00:00:00+00:00",
        fallback_used=False,
    )

    path = service.save_viral_prediction(video_id=14, result=result)

    assert path is not None
    saved = service.load_viral_prediction(14)
    assert saved["viral_score"] == 91
    assert saved["predicted_ctr"] == 88
    assert saved["publish_recommendation"] is True
    assert saved["reasons"] == ["strong hook"]


def test_publisher_decision_metadata_saved_correctly(tmp_path: Path) -> None:
    service = GenerationMetadataService(output_dir=str(tmp_path))
    result = PublisherDecisionResult(
        publish=True,
        confidence=88,
        overall_score=91,
        expected_views=2500,
        expected_ctr=87,
        expected_retention=89,
        risk_level="Low",
        strengths=["strong hook"],
        weaknesses=["minor thumbnail risk"],
        improvements=["tighten thumbnail text"],
        recommended_publish_time="18:00",
        recommended_day="Friday",
        reasoning="Strong package.",
        analysis_timestamp="2026-06-30T00:00:00+00:00",
        fallback_used=False,
    )

    path = service.save_publisher_decision(video_id=16, result=result)

    assert path is not None
    saved = service.load_publisher_decision(16)
    assert saved["publish"] is True
    assert saved["overall_score"] == 91
    assert saved["expected_ctr"] == 87
    assert saved["recommended_publish_time"] == "18:00"


def test_youtube_upload_metadata_saved_correctly(tmp_path: Path) -> None:
    service = GenerationMetadataService(output_dir=str(tmp_path))
    result = YouTubeUploadResult(
        youtube_video_id="youtube-real-id",
        youtube_url="https://www.youtube.com/watch?v=youtube-real-id",
        thumbnail_url="https://img.youtube.com/vi/youtube-real-id/maxresdefault.jpg",
        published_at="2026-07-02T18:00:00Z",
        upload_time=2.5,
        processing_status="processing",
        progress=100,
    )

    path = service.save_youtube_upload(video_id=17, result=result)

    assert path is not None
    saved = service.load_youtube_upload(17)
    assert saved["upload_status"] == "uploaded"
    assert saved["video_id"] == "youtube-real-id"
    assert saved["video_url"] == "https://www.youtube.com/watch?v=youtube-real-id"
    assert saved["processing_status"] == "processing"
    assert saved["progress"] == 100


def test_script_variants_metadata_saved_correctly(tmp_path: Path) -> None:
    service = GenerationMetadataService(output_dir=str(tmp_path))
    analysis = AudienceRetentionAnalysis(
        overall_retention_score=92,
        opening_strength=91,
        first_5_seconds=90,
        curiosity_gap=93,
        story_flow=94,
        information_density=88,
        pace=90,
        emotional_trigger=87,
        ending_strength=89,
        drop_risk="low",
        predicted_drop_points=[],
        improvements=[],
        strengths=["strong"],
    )
    score = ScriptScore(
        hook=92,
        clarity=92,
        retention=92,
        storytelling=92,
        cta=92,
        overall=92,
        strengths=["strong"],
        improvements=[],
    )
    evaluation = ScriptVersionEvaluation(
        label="B",
        focus="Storytelling",
        draft_script="draft",
        reviewed_script="reviewed",
        script_score=score,
        content_intelligence=analysis,
        hook_score=90,
        overall_score=95,
    )
    selection = VersionSelectionResult(
        winner="B",
        scores={"A": 91, "B": 95, "C": 89},
        reason="Highest retention.",
        evaluations=[evaluation],
        best_hook="Best hook",
    )

    path = service.save_script_variants(script_id=15, selection=selection)

    assert path is not None
    saved = service.load_script_variants(15)
    assert saved["winner"] == "B"
    assert saved["version_scores"] == {"A": 91, "B": 95, "C": 89}
    assert saved["selection_reason"] == "Highest retention."
    assert saved["best_hook"] == "Best hook"
