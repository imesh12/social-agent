import logging

from pydantic import BaseModel, Field

from services.google_trends_service import GoogleTrendsService
from services.news_service import HackerNewsService, NewsAPIService
from services.reddit_service import RedditService
from services.trend_ranker_service import TopicSignal, TrendRankerService

logger = logging.getLogger(__name__)


class TrendResult(BaseModel):
    topic: str = Field(min_length=1)
    score: int = Field(ge=0, le=100)


class TrendAgent:
    """Aggregate trend candidates from external sources and return the strongest topic."""

    def __init__(
        self,
        reddit_service: RedditService,
        google_trends_service: GoogleTrendsService,
        hacker_news_service: HackerNewsService | None = None,
        news_api_service: NewsAPIService | None = None,
        trend_ranker_service: TrendRankerService | None = None,
    ) -> None:
        self.reddit_service = reddit_service
        self.google_trends_service = google_trends_service
        self.hacker_news_service = hacker_news_service or HackerNewsService()
        self.news_api_service = news_api_service or NewsAPIService()
        self.trend_ranker_service = trend_ranker_service or TrendRankerService()

    def find_trending_topic(self) -> TrendResult:
        """Return the highest ranked trending topic while tolerating source failures."""
        ranked_topics = self.find_top_trending_topics(limit=3)
        if not ranked_topics:
            logger.warning("No trend sources returned topics; falling back to default topic")
            return TrendResult(topic="AI Tools", score=90)
        best = ranked_topics[0]
        return TrendResult(topic=best["title"], score=best["score"])

    def find_top_trending_topics(self, limit: int = 3) -> list[dict[str, str | int]]:
        """Return the top ranked trend candidates from all available sources."""
        signals: list[TopicSignal] = []
        signals.extend(self._safe_fetch("google_trends", self.google_trends_service.fetch_trending_searches))
        signals.extend(self._safe_fetch("reddit", self.reddit_service.fetch_titles))
        signals.extend(self._safe_fetch("hacker_news", self.hacker_news_service.fetch_top_stories))
        signals.extend(self._safe_fetch("news_api", self.news_api_service.fetch_headlines))
        return self.trend_ranker_service.rank_topics(signals, limit=limit)

    def _safe_fetch(self, source: str, fetcher) -> list[TopicSignal]:
        try:
            titles = fetcher()
            return [TopicSignal(title=title, source=source) for title in self._dedupe_titles(titles)]
        except Exception:
            logger.exception("Trend source failed: %s", source)
            return []

    def _dedupe_titles(self, titles: list[str]) -> list[str]:
        seen: set[str] = set()
        unique: list[str] = []
        for title in titles:
            normalized = " ".join(str(title).lower().split())
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique.append(str(title).strip())
        return unique
