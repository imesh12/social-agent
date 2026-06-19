import logging
from collections.abc import Callable

from backend.config import get_settings

logger = logging.getLogger(__name__)


class GoogleTrendsService:
    """Fetch trending search topics from Google Trends via pytrends."""

    def __init__(self, pytrends_factory: Callable[[], object] | None = None) -> None:
        self.settings = get_settings()
        self.pytrends_factory = pytrends_factory

    def region(self) -> str:
        return self.settings.google_trends_region

    def fetch_trending_searches(self) -> list[str]:
        """Return current Google trending searches for the configured region."""
        try:
            pytrends = self._client()
            dataframe = pytrends.trending_searches(pn=self._pytrends_region())
            if dataframe is None or dataframe.empty:
                return []
            return [str(value).strip() for value in dataframe.iloc[:, 0].tolist() if str(value).strip()]
        except Exception:
            logger.exception("Google Trends fetch failed")
            return []

    def _client(self) -> object:
        if self.pytrends_factory is not None:
            return self.pytrends_factory()

        from pytrends.request import TrendReq

        return TrendReq(hl="en-US", tz=360)

    def _pytrends_region(self) -> str:
        region_map = {
            "US": "united_states",
            "UNITED_STATES": "united_states",
            "UK": "united_kingdom",
            "GB": "united_kingdom",
            "JP": "japan",
        }
        configured = self.settings.google_trends_region.strip()
        return region_map.get(configured.upper(), configured.lower())
