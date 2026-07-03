from services.competitor_analysis_service import CompetitorAnalysisService
from tests.fake_llm import FakeLLMService


class TitleSource:
    def __init__(self, titles: list[str], fail: bool = False) -> None:
        self.titles = titles
        self.fail = fail

    def fetch_titles(self) -> list[str]:
        if self.fail:
            raise RuntimeError("source failed")
        return self.titles

    def fetch_top_stories(self) -> list[str]:
        if self.fail:
            raise RuntimeError("source failed")
        return self.titles

    def fetch_headlines(self) -> list[str]:
        if self.fail:
            raise RuntimeError("source failed")
        return self.titles


def test_competitor_analysis_uses_public_titles() -> None:
    source = TitleSource(
        [
            "Top AI tools for creators in 2026",
            "Best AI productivity apps for work",
            "AI tools launch new automation features",
            "Science team studies battery materials",
            "Why AI tools are changing creator workflows",
            "AI tools and the jobs debate",
        ]
    )
    service = CompetitorAnalysisService(
        reddit_service=source,
        hacker_news_service=source,
        news_api_service=source,
        llm_service=FakeLLMService(),
    )

    analysis = service.analyze("AI Tools")

    assert analysis.searched_topic == "AI Tools"
    assert len(analysis.competitor_titles) == 5
    assert "tools" in analysis.repeated_keywords
    assert analysis.unique_video_angle
    assert analysis.originality_score >= 55


def test_competitor_analysis_falls_back_to_llm_when_sources_fail() -> None:
    source = TitleSource([], fail=True)
    service = CompetitorAnalysisService(
        reddit_service=source,
        hacker_news_service=source,
        news_api_service=source,
        llm_service=FakeLLMService(),
    )

    analysis = service.analyze("AI Tools")

    assert analysis.competitor_titles == []
    assert analysis.originality_score == 72
    assert analysis.unique_video_angle == "Show why one practical AI workflow saves creators time."


def test_competitor_analysis_static_fallback_never_raises() -> None:
    source = TitleSource([], fail=True)
    service = CompetitorAnalysisService(
        reddit_service=source,
        hacker_news_service=source,
        news_api_service=source,
        llm_service=FakeLLMService(fail_research=True),
    )

    analysis = service.analyze("AI Tools")

    assert analysis.originality_score == 65
    assert analysis.unique_video_angle
