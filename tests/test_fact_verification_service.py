from services.fact_verification_service import FactVerificationService
from tests.test_script_agent import make_research_result


class NewsSource:
    def __init__(self, headlines: list[str], fail: bool = False) -> None:
        self.headlines = headlines
        self.fail = fail

    def fetch_headlines(self) -> list[str]:
        if self.fail:
            raise RuntimeError("news failed")
        return self.headlines


def test_successful_fact_verification_with_official_sources() -> None:
    research = make_research_result()
    research.official_sources = ["OpenAI AI tools productivity"]
    service = FactVerificationService()

    result = service.verify(research)

    assert result.fallback_used is False
    assert result.verified_claims
    assert result.rejected_claims == []
    assert result.overall_confidence >= 60
    assert "OpenAI AI tools productivity" in result.sources_checked


def test_partial_fact_verification_rejects_unsupported_specific_claim() -> None:
    research = make_research_result()
    research.interesting_facts = [
        "AI tools help creators move faster.",
        "AI tools are guaranteed to improve output by 90 percent.",
        "Automation can support writing, editing, and repurposing.",
    ]
    research.official_sources = ["OpenAI AI tools creators"]
    service = FactVerificationService()

    result = service.verify(research)

    assert "AI tools help creators move faster." in result.verified_claims
    assert "AI tools are guaranteed to improve output by 90 percent." in result.rejected_claims
    assert result.fallback_used is False


def test_fact_verification_fallback_when_sources_unavailable() -> None:
    research = make_research_result()
    research.official_sources = []
    service = FactVerificationService(news_api_service=NewsSource([], fail=True))

    result = service.verify(research)

    assert result.fallback_used is True
    assert result.verified_claims
    assert result.rejected_claims == []
    assert result.overall_confidence == 55
