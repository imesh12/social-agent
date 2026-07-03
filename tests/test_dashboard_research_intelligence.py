from pathlib import Path


def test_dashboard_contains_research_intelligence_metadata_fields() -> None:
    html = Path("frontend/index.html").read_text(encoding="utf-8")
    javascript = Path("frontend/app.js").read_text(encoding="utf-8")

    assert "Research Intelligence" in html
    assert "originalityScore" in html
    assert "chosenVideoAngle" in html
    assert "missingAngles" in html
    assert "competitorCount" in html
    assert "metadata.originality_score" in javascript
    assert "metadata.chosen_video_angle" in javascript
    assert "metadata.missing_angles" in javascript
    assert "metadata.competitors_analyzed" in javascript


def test_dashboard_contains_fact_verification_metadata_fields() -> None:
    html = Path("frontend/index.html").read_text(encoding="utf-8")
    javascript = Path("frontend/app.js").read_text(encoding="utf-8")

    assert "Fact Verification" in html
    assert "overallConfidence" in html
    assert "claimsVerified" in html
    assert "claimsRejected" in html
    assert "sourcesChecked" in html
    assert "verificationFallback" in html
    assert "metadata.overall_confidence" in javascript
    assert "metadata.verified_claims" in javascript
    assert "metadata.rejected_claims" in javascript
    assert "metadata.verification_sources" in javascript
    assert "metadata.verification_fallback_used" in javascript


def test_dashboard_contains_hook_intelligence_metadata_fields() -> None:
    html = Path("frontend/index.html").read_text(encoding="utf-8")
    javascript = Path("frontend/app.js").read_text(encoding="utf-8")

    assert "Hook Intelligence" in html
    assert "selectedHook" in html
    assert "hookType" in html
    assert "hookOverallScore" in html
    assert "topHooks" in html
    assert "metadata.selected_hook" in javascript
    assert "metadata.hook_type" in javascript
    assert "metadata.hook_scores" in javascript
    assert "metadata.top_hooks" in javascript


def test_dashboard_contains_content_intelligence_metadata_fields() -> None:
    html = Path("frontend/index.html").read_text(encoding="utf-8")
    javascript = Path("frontend/app.js").read_text(encoding="utf-8")

    assert "Content Intelligence" in html
    assert "retentionScore" in html
    assert "openingStrength" in html
    assert "storyFlow" in html
    assert "curiosityGap" in html
    assert "paceScore" in html
    assert "endingStrength" in html
    assert "dropRisk" in html
    assert "contentImprovements" in html
    assert "metadata.content_intelligence" in javascript
    assert "overall_retention_score" in javascript
    assert "opening_strength" in javascript


def test_dashboard_contains_thumbnail_intelligence_metadata_fields() -> None:
    html = Path("frontend/index.html").read_text(encoding="utf-8")
    javascript = Path("frontend/app.js").read_text(encoding="utf-8")

    assert "Thumbnail Intelligence" in html
    assert "thumbnailOverall" in html
    assert "thumbnailCtr" in html
    assert "thumbnailCuriosity" in html
    assert "thumbnailEmotion" in html
    assert "thumbnailContrast" in html
    assert "thumbnailReadability" in html
    assert "thumbnailMobile" in html
    assert "thumbnailAttempts" in html
    assert "thumbnailAccepted" in html
    assert "metadata.thumbnail_intelligence" in javascript
    assert "recommended_changes" in javascript


def test_dashboard_contains_seo_intelligence_metadata_fields() -> None:
    html = Path("frontend/index.html").read_text(encoding="utf-8")
    javascript = Path("frontend/app.js").read_text(encoding="utf-8")

    assert "SEO Intelligence" in html
    assert "seoOverall" in html
    assert "seoTitleScore" in html
    assert "seoCtr" in html
    assert "seoSearchIntent" in html
    assert "seoKeywords" in html
    assert "seoCompetition" in html
    assert "seoDescriptionScore" in html
    assert "seoTagsScore" in html
    assert "seoAccepted" in html
    assert "seoAttempts" in html
    assert "metadata.seo_intelligence" in javascript


def test_dashboard_contains_viral_prediction_metadata_fields() -> None:
    html = Path("frontend/index.html").read_text(encoding="utf-8")
    javascript = Path("frontend/app.js").read_text(encoding="utf-8")

    assert "Viral Prediction" in html
    assert "viralScore" in html
    assert "viralCtr" in html
    assert "viralRetention" in html
    assert "viralRecommendation" in html
    assert "viralConfidence" in html
    assert "viralReasons" in html
    assert "viralImprovements" in html
    assert "metadata.viral_prediction" in javascript


def test_dashboard_contains_publisher_decision_metadata_fields() -> None:
    html = Path("frontend/index.html").read_text(encoding="utf-8")
    javascript = Path("frontend/app.js").read_text(encoding="utf-8")

    assert "Publisher Decision" in html
    assert "publisherOverall" in html
    assert "publisherConfidence" in html
    assert "publisherRecommendation" in html
    assert "publisherRisk" in html
    assert "publisherViews" in html
    assert "publisherCtr" in html
    assert "publisherRetention" in html
    assert "publisherTime" in html
    assert "publisherStrengths" in html
    assert "publisherWeaknesses" in html
    assert "publisherImprovements" in html
    assert "metadata.publisher_decision" in javascript


def test_dashboard_contains_youtube_upload_metadata_fields() -> None:
    html = Path("frontend/index.html").read_text(encoding="utf-8")
    javascript = Path("frontend/app.js").read_text(encoding="utf-8")

    assert "YouTube Upload" in html
    assert "uploadStatus" in html
    assert "uploadProgress" in html
    assert "youtubeVideoUrl" in html
    assert "openYoutube" in html
    assert "uploadTime" in html
    assert "processingStatus" in html
    assert "metadata.youtube_upload" in javascript
    assert "upload_status" in javascript
    assert "video_url" in javascript


def test_dashboard_contains_creative_versions_metadata_fields() -> None:
    html = Path("frontend/index.html").read_text(encoding="utf-8")
    javascript = Path("frontend/app.js").read_text(encoding="utf-8")

    assert "Creative Versions" in html
    assert "versionWinner" in html
    assert "versionScores" in html
    assert "versionReason" in html
    assert "versionCount" in html
    assert "versionBestHook" in html
    assert "metadata.script_variants" in javascript
    assert "version_scores" in javascript
