from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from services.competitor_analysis_service import CompetitorAnalysis
from services.content_intelligence_service import AudienceRetentionAnalysis
from services.fact_verification_service import FactVerificationResult
from services.seo_intelligence_service import SEOIntelligenceResult
from services.thumbnail_intelligence_service import ThumbnailIntelligenceResult
from services.viral_prediction_service import ViralPredictionResult
from services.publisher_decision_service import PublisherDecisionResult


class LLMResearchResult(BaseModel):
    """Creator-focused research package for short-form video generation."""

    topic: str = Field(min_length=1)
    category: str = Field(min_length=1)
    target_audience: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    interesting_facts: list[str] = Field(min_length=3, max_length=5)
    statistics: list[str] = Field(default_factory=list)
    misconceptions: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    official_sources: list[str] = Field(default_factory=list)
    video_angle: str = Field(min_length=1)
    hook_ideas: list[str] = Field(min_length=3, max_length=3)
    cta_ideas: list[str] = Field(min_length=3, max_length=3)
    competitor_analysis: CompetitorAnalysis | None = None
    fact_verification: FactVerificationResult | None = None
    selected_hook: str | None = None
    top_hooks: list[str] = Field(default_factory=list)
    selection_reason: str | None = None

    @property
    def facts(self) -> list[str]:
        """Backward-compatible access to the core research facts."""
        return self.interesting_facts


class LLMSEOResult(BaseModel):
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    tags: list[str] = Field(min_length=1)
    hashtags: str = Field(min_length=1)


class ScriptScore(BaseModel):
    """Quality score for a generated short-form script."""

    hook: int = Field(ge=0, le=100)
    clarity: int = Field(ge=0, le=100)
    retention: int = Field(ge=0, le=100)
    storytelling: int = Field(ge=0, le=100)
    cta: int = Field(ge=0, le=100)
    overall: int = Field(ge=0, le=100)
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)

    def score_summary(self) -> dict[str, int]:
        """Return the compact score fields used by generation metadata."""
        return {
            "hook": self.hook,
            "clarity": self.clarity,
            "retention": self.retention,
            "storytelling": self.storytelling,
            "cta": self.cta,
            "overall": self.overall,
        }


class ScriptVariant(BaseModel):
    """One creative script version from multi-version generation."""

    focus: str = Field(min_length=1)
    script: str = Field(min_length=1)


class ScriptVariants(BaseModel):
    """Three creative script versions for independent evaluation."""

    version_a: ScriptVariant
    version_b: ScriptVariant
    version_c: ScriptVariant


class BaseLLMService(ABC):
    @abstractmethod
    def research(self, topic: str, competitor_analysis: CompetitorAnalysis | None = None) -> LLMResearchResult:
        raise NotImplementedError

    @abstractmethod
    def generate_script(self, research: LLMResearchResult) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_script_variants(self, research: LLMResearchResult) -> ScriptVariants:
        raise NotImplementedError

    @abstractmethod
    def review_script(self, script: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def score_script(self, script: str) -> ScriptScore:
        raise NotImplementedError

    @abstractmethod
    def analyze_content_intelligence(self, script: str) -> AudienceRetentionAnalysis:
        raise NotImplementedError

    @abstractmethod
    def analyze_thumbnail_intelligence(self, thumbnail_path: str) -> ThumbnailIntelligenceResult:
        raise NotImplementedError

    @abstractmethod
    def analyze_seo_intelligence(self, script_text: str, seo: LLMSEOResult) -> SEOIntelligenceResult:
        raise NotImplementedError

    @abstractmethod
    def improve_seo(self, script_text: str, seo: LLMSEOResult, analysis: SEOIntelligenceResult) -> LLMSEOResult:
        raise NotImplementedError

    @abstractmethod
    def analyze_viral_prediction(self, content_package: dict) -> ViralPredictionResult:
        raise NotImplementedError

    @abstractmethod
    def analyze_publisher_decision(self, content_package: dict) -> PublisherDecisionResult:
        raise NotImplementedError

    @abstractmethod
    def generate_seo(self, script_text: str) -> LLMSEOResult:
        raise NotImplementedError
