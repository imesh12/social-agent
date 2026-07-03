import re
import time
from typing import Any, Protocol

from pydantic import BaseModel, Field

from services.utils.logging import get_rotating_logger

verification_logger = get_rotating_logger("fact_verification", "fact_verification.log")


class ClaimVerificationDetail(BaseModel):
    """Verification status for one factual claim."""

    claim: str = Field(min_length=1)
    status: str = Field(min_length=1)
    confidence: int = Field(ge=0, le=100)
    source: str = Field(default="")
    notes: str = Field(default="")


class FactVerificationResult(BaseModel):
    """Structured verification result attached to a research package."""

    verified_claims: list[str] = Field(default_factory=list)
    rejected_claims: list[str] = Field(default_factory=list)
    verification_summary: str = Field(default="")
    overall_confidence: int = Field(ge=0, le=100)
    sources_checked: list[str] = Field(default_factory=list)
    verification_time: float = Field(ge=0)
    fallback_used: bool = False
    claim_details: list[ClaimVerificationDetail] = Field(default_factory=list)


class NewsVerificationSource(Protocol):
    """Protocol for existing public headline services."""

    def fetch_headlines(self) -> list[str]:
        raise NotImplementedError


class FactVerificationService:
    """Verify research claims before they are used for script generation."""

    official_domains = (
        "openai.com",
        "google.com",
        "microsoft.com",
        "apple.com",
        "nvidia.com",
        "meta.com",
        "anthropic.com",
        "youtube.com",
        "tiktok.com",
        "instagram.com",
    )

    def __init__(self, news_api_service: NewsVerificationSource | None = None) -> None:
        self.news_api_service = news_api_service

    def verify(self, research_package: Any) -> FactVerificationResult:
        """Verify research claims and fail soft on every error."""
        started_at = time.perf_counter()
        topic = str(getattr(research_package, "topic", "unknown"))
        try:
            claims = self._claims_from_package(research_package)
            official_sources = self._official_sources(getattr(research_package, "official_sources", []))
            news_headlines = self._news_headlines(topic)
            sources_checked = official_sources + (["News API headlines"] if news_headlines else [])

            if not sources_checked:
                return self._fallback_result(topic=topic, claims=claims, started_at=started_at)

            details = [
                self._verify_claim(
                    claim=claim,
                    official_sources=official_sources,
                    news_headlines=news_headlines,
                )
                for claim in claims
            ]
            verified = [detail.claim for detail in details if detail.status == "verified"]
            rejected = [detail.claim for detail in details if detail.status == "rejected"]
            confidence = self._overall_confidence(details)
            result = FactVerificationResult(
                verified_claims=verified,
                rejected_claims=rejected,
                verification_summary=f"Verified {len(verified)} of {len(claims)} claims using available official/public sources.",
                overall_confidence=confidence,
                sources_checked=sources_checked,
                verification_time=round(time.perf_counter() - started_at, 4),
                fallback_used=False,
                claim_details=details,
            )
            verification_logger.info(
                "Fact verification topic=%s claims_checked=%s verified=%s rejected=%s overall_confidence=%s fallback_usage=%s",
                topic,
                len(claims),
                len(verified),
                len(rejected),
                confidence,
                False,
            )
            return result
        except Exception:
            verification_logger.exception("Fact verification failed topic=%s; using fallback", topic)
            return self._fallback_result(
                topic=topic,
                claims=self._claims_from_package(research_package),
                started_at=started_at,
            )

    def _verify_claim(
        self,
        claim: str,
        official_sources: list[str],
        news_headlines: list[str],
    ) -> ClaimVerificationDetail:
        claim_tokens = set(self._tokens(claim))
        risky_specific = self._has_risky_specifics(claim)
        official_match = self._best_source_match(claim_tokens, official_sources)
        if risky_specific and official_match and self._specific_source_supports_claim(claim, official_match):
            return ClaimVerificationDetail(
                claim=claim,
                status="verified",
                confidence=88,
                source=official_match,
                notes="Specific claim matched against an official source.",
            )
        if risky_specific and official_match:
            return ClaimVerificationDetail(
                claim=claim,
                status="rejected",
                confidence=35,
                source=official_match,
                notes="Broad source overlap was not enough to support a specific statistic or superlative.",
            )
        if official_match:
            return ClaimVerificationDetail(
                claim=claim,
                status="verified",
                confidence=90,
                source=official_match,
                notes="Matched against an official source listed in the research package.",
            )

        news_match = self._best_source_match(claim_tokens, news_headlines)
        if risky_specific and news_match and not self._specific_source_supports_claim(claim, news_match):
            return ClaimVerificationDetail(
                claim=claim,
                status="rejected",
                confidence=35,
                source="News API headlines",
                notes="Related headline did not support the specific statistic or superlative.",
            )
        if news_match:
            return ClaimVerificationDetail(
                claim=claim,
                status="verified",
                confidence=78,
                source="News API headlines",
                notes=f"Supported by related headline: {news_match}",
            )

        if risky_specific:
            return ClaimVerificationDetail(
                claim=claim,
                status="rejected",
                confidence=35,
                source="",
                notes="Specific statistic or superlative was not supported by available sources.",
            )

        return ClaimVerificationDetail(
            claim=claim,
            status="estimated",
            confidence=62,
            source="LLM reasoning estimate",
            notes="No official source match was available; treat as estimated and avoid unsupported precision.",
        )

    def _specific_source_supports_claim(self, claim: str, source: str) -> bool:
        claim_numbers = set(re.findall(r"\d+(?:\.\d+)?", claim.lower()))
        source_numbers = set(re.findall(r"\d+(?:\.\d+)?", source.lower()))
        if claim_numbers:
            return bool(claim_numbers & source_numbers)
        claim_specifics = {"first", "only", "always", "never", "most", "biggest", "largest", "guaranteed"}
        source_tokens = set(self._tokens(source))
        return bool(set(self._tokens(claim)) & claim_specifics & source_tokens)

    def _fallback_result(
        self,
        topic: str,
        claims: list[str],
        started_at: float,
    ) -> FactVerificationResult:
        details = [
            ClaimVerificationDetail(
                claim=claim,
                status="estimated",
                confidence=55,
                source="LLM reasoning estimate",
                notes="Verification fallback used; claim is not independently confirmed.",
            )
            for claim in claims
        ]
        result = FactVerificationResult(
            verified_claims=claims,
            rejected_claims=[],
            verification_summary="Verification used fallback reasoning because official sources were unavailable.",
            overall_confidence=55 if claims else 0,
            sources_checked=[],
            verification_time=round(time.perf_counter() - started_at, 4),
            fallback_used=True,
            claim_details=details,
        )
        verification_logger.info(
            "Fact verification topic=%s claims_checked=%s verified=%s rejected=%s overall_confidence=%s fallback_usage=%s",
            topic,
            len(claims),
            len(result.verified_claims),
            0,
            result.overall_confidence,
            True,
        )
        return result

    def _claims_from_package(self, research_package: Any) -> list[str]:
        values = list(getattr(research_package, "interesting_facts", []) or [])
        values.extend(getattr(research_package, "statistics", []) or [])
        return [str(value).strip() for value in values if str(value).strip()]

    def _official_sources(self, sources: list[str]) -> list[str]:
        official: list[str] = []
        for source in sources or []:
            normalized = str(source).strip()
            lower = normalized.lower()
            if normalized and (
                any(domain in lower for domain in self.official_domains)
                or not re.search(r"https?://", lower)
            ):
                official.append(normalized)
        return official

    def _news_headlines(self, topic: str) -> list[str]:
        if self.news_api_service is None:
            return []
        try:
            headlines = self.news_api_service.fetch_headlines()
            topic_tokens = set(self._tokens(topic))
            return [
                headline
                for headline in headlines
                if not topic_tokens or set(self._tokens(headline)) & topic_tokens
            ]
        except Exception:
            verification_logger.exception("News verification source failed topic=%s", topic)
            return []

    def _best_source_match(self, claim_tokens: set[str], sources: list[str]) -> str:
        if not claim_tokens:
            return ""
        best_source = ""
        best_overlap = 0
        for source in sources:
            overlap = len(claim_tokens & set(self._tokens(source)))
            if overlap > best_overlap:
                best_overlap = overlap
                best_source = source
        return best_source if best_overlap >= 1 else ""

    def _has_risky_specifics(self, claim: str) -> bool:
        lower = claim.lower()
        return bool(
            re.search(r"\b\d+(\.\d+)?\s?(%|percent|million|billion|x)\b", lower)
            or re.search(r"\b(first|only|always|never|most|biggest|largest|guaranteed)\b", lower)
        )

    def _overall_confidence(self, details: list[ClaimVerificationDetail]) -> int:
        if not details:
            return 0
        return round(sum(detail.confidence for detail in details) / len(details))

    def _tokens(self, text: str) -> list[str]:
        stopwords = {
            "the",
            "and",
            "for",
            "with",
            "from",
            "this",
            "that",
            "are",
            "you",
            "your",
            "how",
            "why",
            "what",
            "new",
            "top",
            "best",
            "using",
            "used",
            "users",
        }
        return [
            token
            for token in re.findall(r"[a-z0-9]+", text.lower())
            if len(token) > 2 and token not in stopwords
        ]
