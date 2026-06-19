import logging
from typing import Any

import requests

from backend.config import get_settings

logger = logging.getLogger(__name__)


class HackerNewsService:
    """Fetch top story titles from the official Hacker News Firebase API."""

    base_url = "https://hacker-news.firebaseio.com/v0"

    def __init__(self, http_client: Any | None = None) -> None:
        self.http_client = http_client or requests.Session()

    def fetch_top_stories(self, limit: int = 20) -> list[str]:
        """Return top Hacker News story titles."""
        try:
            response = self.http_client.get(f"{self.base_url}/topstories.json", timeout=15)
            response.raise_for_status()
            story_ids = response.json()[:limit]
        except Exception:
            logger.exception("Hacker News top stories fetch failed")
            return []

        titles: list[str] = []
        for story_id in story_ids:
            try:
                response = self.http_client.get(f"{self.base_url}/item/{story_id}.json", timeout=15)
                response.raise_for_status()
                title = str(response.json().get("title", "")).strip()
                if title:
                    titles.append(title)
            except Exception:
                logger.exception("Hacker News item fetch failed for id=%s", story_id)
                continue
        return titles


class NewsAPIService:
    """Fetch technology headlines from News API."""

    def __init__(self, http_client: Any | None = None) -> None:
        self.settings = get_settings()
        self.http_client = http_client or requests.Session()

    def fetch_headlines(self, page_size: int = 20) -> list[str]:
        """Return News API article titles, or an empty list when not configured."""
        if not self.settings.news_api_key:
            logger.warning("NEWS_API_KEY is not configured; skipping News API")
            return []

        try:
            response = self.http_client.get(
                f"{self.settings.news_api_base_url.rstrip('/')}/top-headlines",
                params={
                    "category": "technology",
                    "language": "en",
                    "pageSize": page_size,
                    "apiKey": self.settings.news_api_key,
                },
                timeout=15,
            )
            response.raise_for_status()
            articles = response.json().get("articles", [])
            return [
                str(article.get("title", "")).strip()
                for article in articles
                if str(article.get("title", "")).strip()
            ]
        except Exception:
            logger.exception("News API fetch failed")
            return []
