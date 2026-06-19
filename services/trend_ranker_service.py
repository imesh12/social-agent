import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import TypedDict


class RankedTrend(TypedDict):
    title: str
    source: str
    score: int


@dataclass(frozen=True)
class TopicSignal:
    """A normalized topic candidate produced by one trend source."""

    title: str
    source: str
    engagement: float = 1.0
    recency: float = 1.0


class TrendRankerService:
    """Rank topic candidates using frequency, recency, engagement, and keyword quality."""

    quality_keywords = {
        "ai",
        "artificial intelligence",
        "chatgpt",
        "technology",
        "science",
        "startup",
        "tools",
        "automation",
        "robot",
        "software",
    }

    def rank_topics(self, topics: list[str] | list[TopicSignal], limit: int = 3) -> list[RankedTrend]:
        """Return ranked trend dictionaries sorted by highest score."""
        signals = self._coerce_signals(topics)
        if not signals:
            return []

        grouped: dict[str, list[TopicSignal]] = defaultdict(list)
        display_titles: dict[str, str] = {}
        for signal in signals:
            key = self._dedupe_key(signal.title)
            grouped[key].append(signal)
            display_titles.setdefault(key, signal.title)

        max_frequency = max(len(values) for values in grouped.values())
        max_engagement = max(sum(signal.engagement for signal in values) for values in grouped.values()) or 1.0

        ranked: list[RankedTrend] = []
        for key, values in grouped.items():
            frequency_score = len(values) / max_frequency
            recency_score = sum(signal.recency for signal in values) / len(values)
            engagement_score = sum(signal.engagement for signal in values) / max_engagement
            keyword_score = self._keyword_quality(display_titles[key])
            total = (
                0.4 * frequency_score
                + 0.3 * recency_score
                + 0.2 * engagement_score
                + 0.1 * keyword_score
            )
            source = self._source_label(values)
            ranked.append(
                {
                    "title": display_titles[key],
                    "source": source,
                    "score": max(1, min(100, int(round(total * 100)))),
                }
            )

        return sorted(ranked, key=lambda item: item["score"], reverse=True)[:limit]

    def _coerce_signals(self, topics: list[str] | list[TopicSignal]) -> list[TopicSignal]:
        signals: list[TopicSignal] = []
        for topic in topics:
            if isinstance(topic, TopicSignal):
                title = topic.title.strip()
                if title:
                    signals.append(topic)
            else:
                title = str(topic).strip()
                if title:
                    signals.append(TopicSignal(title=title, source="unknown"))
        return signals

    def _dedupe_key(self, title: str) -> str:
        normalized = re.sub(r"[^a-z0-9\s]", " ", title.lower())
        words = [word for word in normalized.split() if len(word) > 2]
        return " ".join(words[:8]) or normalized.strip()

    def _keyword_quality(self, title: str) -> float:
        lower = title.lower()
        matches = sum(1 for keyword in self.quality_keywords if keyword in lower)
        if matches == 0:
            return 0.35
        return min(1.0, 0.55 + math.log1p(matches) / 2)

    def _source_label(self, values: list[TopicSignal]) -> str:
        counts = Counter(signal.source for signal in values)
        if len(counts) == 1:
            return next(iter(counts))
        return "multiple"
