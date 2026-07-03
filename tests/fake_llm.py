from services.competitor_analysis_service import CompetitorAnalysis
from services.content_intelligence_service import AudienceRetentionAnalysis
from services.llm.base_llm_service import BaseLLMService, LLMResearchResult, LLMSEOResult, ScriptScore, ScriptVariant, ScriptVariants
from services.publisher_decision_service import PublisherDecisionResult
from services.seo_intelligence_service import SEOIntelligenceResult
from services.thumbnail_intelligence_service import ThumbnailIntelligenceResult
from services.viral_prediction_service import ViralPredictionResult


class FakeLLMService(BaseLLMService):
    def __init__(
        self,
        reviewed_script: str | None = None,
        fail_review: bool = False,
        fail_research: bool = False,
        fail_score: bool = False,
        fail_script_variants: bool = True,
        fail_content_intelligence: bool = False,
        fail_thumbnail_intelligence: bool = False,
        fail_seo_intelligence: bool = False,
        fail_seo_improvement: bool = False,
        fail_viral_prediction: bool = False,
        fail_publisher_decision: bool = False,
        score_sequence: list[ScriptScore] | None = None,
        script_variants: ScriptVariants | None = None,
        thumbnail_score_sequence: list[ThumbnailIntelligenceResult] | None = None,
        seo_score_sequence: list[SEOIntelligenceResult] | None = None,
        viral_prediction: ViralPredictionResult | None = None,
        publisher_decision: PublisherDecisionResult | None = None,
        improved_seo_sequence: list[LLMSEOResult] | None = None,
        script_drafts: list[str] | None = None,
    ) -> None:
        self.reviewed_script = reviewed_script
        self.fail_review = fail_review
        self.fail_research = fail_research
        self.fail_score = fail_score
        self.fail_script_variants = fail_script_variants
        self.fail_content_intelligence = fail_content_intelligence
        self.fail_thumbnail_intelligence = fail_thumbnail_intelligence
        self.fail_seo_intelligence = fail_seo_intelligence
        self.fail_seo_improvement = fail_seo_improvement
        self.fail_viral_prediction = fail_viral_prediction
        self.fail_publisher_decision = fail_publisher_decision
        self.score_sequence = score_sequence or [
            ScriptScore(
                hook=91,
                clarity=91,
                retention=91,
                storytelling=91,
                cta=91,
                overall=91,
                strengths=["Strong hook"],
                improvements=[],
            )
        ]
        self.script_drafts = script_drafts or []
        self.script_variants = script_variants or ScriptVariants(
            version_a=ScriptVariant(
                focus="High curiosity",
                script="Most people miss this AI workflow. Here is why it matters. Follow for more.",
            ),
            version_b=ScriptVariant(
                focus="Storytelling",
                script="A creator opens a blank page. AI handles the boring draft. Try it today.",
            ),
            version_c=ScriptVariant(
                focus="Fast educational delivery",
                script="Use AI for drafts, edits, and summaries. Start small. Save this workflow.",
            ),
        )
        self.thumbnail_score_sequence = thumbnail_score_sequence or [
            ThumbnailIntelligenceResult(
                overall_score=90,
                ctr_prediction=88,
                curiosity_score=87,
                emotion_score=84,
                contrast_score=91,
                visual_clarity=89,
                mobile_visibility=88,
                text_readability=90,
                subject_focus=86,
                brand_consistency=82,
                recommended_changes=["make text shorter"],
                strengths=["clear readable text"],
                weaknesses=["could use stronger subject focus"],
                regeneration_attempt=0,
                accepted=True,
                selected_thumbnail_path="",
                analysis_timestamp="2026-06-30T00:00:00+00:00",
                fallback_used=False,
            )
        ]
        self.seo_score_sequence = seo_score_sequence or [
            SEOIntelligenceResult(
                overall_score=90,
                title_score=90,
                description_score=88,
                keyword_score=89,
                tag_score=87,
                hashtag_score=88,
                search_intent_score=90,
                ctr_prediction=89,
                competition_level="medium",
                readability_score=91,
                engagement_score=86,
                recommended_title="Top 3 AI Tools You Need In 2026 #shorts",
                recommended_description="Discover AI tools changing productivity.",
                recommended_tags=["AI", "ChatGPT", "Technology"],
                recommended_hashtags="#ai #shorts #technology",
                strengths=["clear search intent"],
                weaknesses=["could be more specific"],
                recommended_changes=["make title more specific"],
                accepted=True,
                attempt=0,
                analysis_timestamp="2026-06-30T00:00:00+00:00",
                fallback_used=False,
            )
        ]
        self.improved_seo_sequence = improved_seo_sequence or []
        self.viral_prediction = viral_prediction or ViralPredictionResult(
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
            reasons=["strong hook", "clear thumbnail", "good SEO alignment"],
            improvements=["increase emotional contrast"],
            analysis_timestamp="2026-06-30T00:00:00+00:00",
            fallback_used=False,
        )
        self.publisher_decision = publisher_decision or PublisherDecisionResult(
            publish=True,
            confidence=88,
            overall_score=91,
            expected_views=2500,
            expected_ctr=87,
            expected_retention=89,
            risk_level="Low",
            strengths=["strong hook", "clear retention signals"],
            weaknesses=["minor thumbnail risk"],
            improvements=["tighten thumbnail text"],
            recommended_publish_time="18:00",
            recommended_day="Friday",
            reasoning="The package has strong retention and low risk.",
            analysis_timestamp="2026-06-30T00:00:00+00:00",
            fallback_used=False,
        )
        self.review_called = False
        self.score_called = False
        self.score_calls = 0
        self.content_intelligence_called = False
        self.thumbnail_intelligence_called = False
        self.thumbnail_intelligence_calls = 0
        self.seo_intelligence_called = False
        self.seo_intelligence_calls = 0
        self.seo_improvement_calls = 0
        self.viral_prediction_called = False
        self.publisher_decision_called = False
        self.generate_script_calls = 0
        self.generate_script_variants_called = False
        self.last_script_research: LLMResearchResult | None = None

    def research(
        self,
        topic: str,
        competitor_analysis: CompetitorAnalysis | None = None,
    ) -> LLMResearchResult:
        if self.fail_research:
            raise RuntimeError("research failed")
        analysis = competitor_analysis or CompetitorAnalysis(
            searched_topic=topic,
            competitor_titles=["Top AI tools everyone is using"],
            common_angles=["tool list or roundup"],
            repeated_keywords=["tools", "ai"],
            missing_angles=["Show one practical workflow instead of another list."],
            unique_video_angle="Show one practical AI workflow creators can use today.",
            hook_opportunities=["Most AI tool videos miss the actual workflow."],
            credibility_notes=["Fake test analysis."],
            originality_score=88,
        )
        return LLMResearchResult(
            topic=topic,
            category="Technology",
            target_audience="Creators and small business owners",
            summary="AI tools are changing how people create, edit, and repurpose work.",
            why_it_matters="They can help viewers save time without needing advanced technical skills.",
            interesting_facts=[
                "AI productivity tools are being adopted by creators and small businesses.",
                "Automation features help users write, edit, summarize, and repurpose content.",
                "Short-form videos work well when they include clear examples.",
            ],
            statistics=["Short-form videos often perform best when they focus on one clear idea."],
            misconceptions=["AI tools do not replace strategy or taste by default."],
            keywords=["AI", "productivity", "automation"],
            official_sources=["OpenAI", "Google"],
            video_angle="Show why one practical AI workflow saves creators time.",
            hook_ideas=[
                "These AI tools are changing everything.",
                "Most creators miss this simple AI workflow.",
                "This is why AI tools keep getting popular.",
            ],
            cta_ideas=[
                "Which one would you try?",
                "Follow for more simple AI tips.",
                "Save this for your next workflow.",
            ],
            competitor_analysis=analysis,
        )

    def generate_script(self, research: LLMResearchResult) -> str:
        self.last_script_research = research
        self.generate_script_calls += 1
        if self.script_drafts:
            index = min(self.generate_script_calls - 1, len(self.script_drafts) - 1)
            return self.script_drafts[index]
        return (
            'Hook:\n"These AI tools are changing everything."\n\n'
            'Body:\n"Three tools are becoming incredibly popular because they save time."\n\n'
            'Ending:\n"Which one would you try?"'
        )

    def generate_script_variants(self, research: LLMResearchResult) -> ScriptVariants:
        self.generate_script_variants_called = True
        self.last_script_research = research
        if self.fail_script_variants:
            raise RuntimeError("script variants failed")
        return self.script_variants

    def review_script(self, script: str) -> str:
        self.review_called = True
        if self.fail_review:
            raise RuntimeError("review failed")
        return self.reviewed_script or script

    def score_script(self, script: str) -> ScriptScore:
        self.score_called = True
        self.score_calls += 1
        if self.fail_score:
            raise RuntimeError("score failed")
        index = min(self.score_calls - 1, len(self.score_sequence) - 1)
        return self.score_sequence[index]

    def analyze_content_intelligence(self, script: str) -> AudienceRetentionAnalysis:
        self.content_intelligence_called = True
        if self.fail_content_intelligence:
            raise RuntimeError("content intelligence failed")
        return AudienceRetentionAnalysis(
            overall_retention_score=88,
            opening_strength=90,
            first_5_seconds=89,
            curiosity_gap=87,
            story_flow=86,
            information_density=84,
            pace=88,
            emotional_trigger=83,
            ending_strength=85,
            drop_risk="low",
            predicted_drop_points=["sentence 3: explanation may slow down"],
            improvements=["add pattern interrupt", "stronger CTA"],
            strengths=["strong opening", "clear pacing"],
            analysis_timestamp="2026-06-30T00:00:00+00:00",
            fallback_used=False,
        )

    def analyze_thumbnail_intelligence(self, thumbnail_path: str) -> ThumbnailIntelligenceResult:
        self.thumbnail_intelligence_called = True
        self.thumbnail_intelligence_calls += 1
        if self.fail_thumbnail_intelligence:
            raise RuntimeError("thumbnail intelligence failed")
        index = min(self.thumbnail_intelligence_calls - 1, len(self.thumbnail_score_sequence) - 1)
        result = self.thumbnail_score_sequence[index].model_copy(deep=True)
        result.selected_thumbnail_path = thumbnail_path
        return result

    def analyze_seo_intelligence(self, script_text: str, seo: LLMSEOResult) -> SEOIntelligenceResult:
        self.seo_intelligence_called = True
        self.seo_intelligence_calls += 1
        if self.fail_seo_intelligence:
            raise RuntimeError("seo intelligence failed")
        index = min(self.seo_intelligence_calls - 1, len(self.seo_score_sequence) - 1)
        return self.seo_score_sequence[index].model_copy(deep=True)

    def improve_seo(
        self,
        script_text: str,
        seo: LLMSEOResult,
        analysis: SEOIntelligenceResult,
    ) -> LLMSEOResult:
        self.seo_improvement_calls += 1
        if self.fail_seo_improvement:
            raise RuntimeError("seo improvement failed")
        if self.improved_seo_sequence:
            index = min(self.seo_improvement_calls - 1, len(self.improved_seo_sequence) - 1)
            return self.improved_seo_sequence[index]
        return LLMSEOResult(
            title=analysis.recommended_title,
            description=analysis.recommended_description,
            tags=analysis.recommended_tags,
            hashtags=analysis.recommended_hashtags,
        )

    def analyze_viral_prediction(self, content_package: dict) -> ViralPredictionResult:
        self.viral_prediction_called = True
        if self.fail_viral_prediction:
            raise RuntimeError("viral prediction failed")
        return self.viral_prediction.model_copy(deep=True)

    def analyze_publisher_decision(self, content_package: dict) -> PublisherDecisionResult:
        self.publisher_decision_called = True
        if self.fail_publisher_decision:
            raise RuntimeError("publisher decision failed")
        return self.publisher_decision.model_copy(deep=True)

    def generate_seo(self, script_text: str) -> LLMSEOResult:
        return LLMSEOResult(
            title="Top 3 AI Tools You Need In 2026 #shorts",
            description="Discover AI tools changing productivity.",
            tags=["AI", "ChatGPT", "Technology"],
            hashtags="#ai #shorts #technology",
        )
