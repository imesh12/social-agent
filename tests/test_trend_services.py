from dataclasses import dataclass

from services.google_trends_service import GoogleTrendsService
from services.news_service import HackerNewsService, NewsAPIService
from services.reddit_service import RedditService
from services.trend_ranker_service import TopicSignal, TrendRankerService


class FakeDataFrame:
    empty = False

    @property
    def iloc(self):
        return self

    def __getitem__(self, key):
        return self

    def tolist(self) -> list[str]:
        return ["AI tools", "Quantum computing"]


class FakePytrends:
    def trending_searches(self, pn: str):
        assert pn
        return FakeDataFrame()


@dataclass
class FakeResponse:
    payload: object

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


class FakeRedditClient:
    def get(self, url: str, **kwargs):
        return FakeResponse(
            {
                "data": {
                    "children": [
                        {"data": {"title": "New AI tool launches"}},
                        {"data": {"title": "Science breakthrough"}},
                    ]
                }
            }
        )


class FakeHackerNewsClient:
    def get(self, url: str, **kwargs):
        if url.endswith("/topstories.json"):
            return FakeResponse([101, 102])
        if url.endswith("/item/101.json"):
            return FakeResponse({"title": "Open source AI framework"})
        return FakeResponse({"title": "New database benchmark"})


class FakeNewsAPIClient:
    def get(self, url: str, **kwargs):
        return FakeResponse(
            {
                "articles": [
                    {"title": "AI chip startup raises funding"},
                    {"title": "Robotics lab releases new system"},
                ]
            }
        )


def test_google_trends_service_fetches_titles() -> None:
    service = GoogleTrendsService(pytrends_factory=FakePytrends)

    assert service.fetch_trending_searches() == ["AI tools", "Quantum computing"]


def test_reddit_service_fetches_titles() -> None:
    service = RedditService(http_client=FakeRedditClient())

    titles = service.fetch_titles(limit=2)

    assert "New AI tool launches" in titles
    assert "Science breakthrough" in titles


def test_hacker_news_service_fetches_titles() -> None:
    service = HackerNewsService(http_client=FakeHackerNewsClient())

    assert service.fetch_top_stories(limit=2) == [
        "Open source AI framework",
        "New database benchmark",
    ]


def test_news_api_service_fetches_titles(monkeypatch) -> None:
    from backend.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("NEWS_API_KEY", "test-key")
    try:
        service = NewsAPIService(http_client=FakeNewsAPIClient())

        assert service.fetch_headlines(page_size=2) == [
            "AI chip startup raises funding",
            "Robotics lab releases new system",
        ]
    finally:
        get_settings.cache_clear()


def test_trend_ranker_service_ranks_and_deduplicates() -> None:
    ranker = TrendRankerService()

    ranked = ranker.rank_topics(
        [
            TopicSignal(title="AI tools for creators", source="google_trends"),
            TopicSignal(title="AI tools for creators", source="reddit"),
            TopicSignal(title="Gardening tips", source="news_api"),
        ]
    )

    assert ranked[0]["title"] == "AI tools for creators"
    assert ranked[0]["source"] == "multiple"
    assert ranked[0]["score"] > ranked[1]["score"]
