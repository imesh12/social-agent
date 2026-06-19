import logging
from typing import Any

import requests

from backend.config import get_settings

logger = logging.getLogger(__name__)


class RedditService:
    """Fetch trend candidates from public Reddit listing endpoints."""

    subreddits = ("technology", "artificial", "science")

    def __init__(self, http_client: Any | None = None) -> None:
        self.settings = get_settings()
        self.http_client = http_client or requests.Session()

    def is_configured(self) -> bool:
        return bool(self.settings.reddit_client_id and self.settings.reddit_client_secret)

    def fetch_titles(self, limit: int = 15) -> list[str]:
        """Return hot post titles from configured subreddits."""
        titles: list[str] = []
        headers = {"User-Agent": self.settings.reddit_user_agent}
        for subreddit in self.subreddits:
            try:
                response = self.http_client.get(
                    f"https://www.reddit.com/r/{subreddit}/hot.json",
                    params={"limit": limit},
                    headers=headers,
                    timeout=15,
                )
                response.raise_for_status()
                children = response.json().get("data", {}).get("children", [])
                titles.extend(
                    str(child.get("data", {}).get("title", "")).strip()
                    for child in children
                    if str(child.get("data", {}).get("title", "")).strip()
                )
            except Exception:
                logger.exception("Reddit fetch failed for r/%s", subreddit)
                continue
        return titles
