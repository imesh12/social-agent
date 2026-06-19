from agents.trend_agent import TrendAgent
from services.trend_ranker_service import TrendRankerService


class FakeSource:
    def __init__(self, titles: list[str], should_fail: bool = False) -> None:
        self.titles = titles
        self.should_fail = should_fail

    def fetch_trending_searches(self) -> list[str]:
        return self._fetch()

    def fetch_titles(self) -> list[str]:
        return self._fetch()

    def fetch_top_stories(self) -> list[str]:
        return self._fetch()

    def fetch_headlines(self) -> list[str]:
        return self._fetch()

    def _fetch(self) -> list[str]:
        if self.should_fail:
            raise RuntimeError("source down")
        return self.titles


def test_trend_agent_returns_top_topic_and_continues_on_failure() -> None:
    agent = TrendAgent(
        google_trends_service=FakeSource(["AI tools for creators", "Space news"]),
        reddit_service=FakeSource(["AI tools for creators"]),
        hacker_news_service=FakeSource([], should_fail=True),
        news_api_service=FakeSource(["Robotics breakthrough"]),
        trend_ranker_service=TrendRankerService(),
    )

    result = agent.find_trending_topic()

    assert result.topic == "AI tools for creators"
    assert result.score > 0


def test_trend_agent_falls_back_when_all_sources_fail() -> None:
    failing = FakeSource([], should_fail=True)
    agent = TrendAgent(
        google_trends_service=failing,
        reddit_service=failing,
        hacker_news_service=failing,
        news_api_service=failing,
        trend_ranker_service=TrendRankerService(),
    )

    assert agent.find_trending_topic().topic == "AI Tools"
