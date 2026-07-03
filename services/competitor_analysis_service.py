import logging
import re
from collections import Counter
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from services.llm.base_llm_service import BaseLLMService

logger = logging.getLogger(__name__)


class CompetitorAnalysis(BaseModel):
    """Content-gap analysis for a topic before script generation."""

    searched_topic: str = Field(min_length=1)
    competitor_titles: list[str] = Field(default_factory=list, max_length=5)
    common_angles: list[str] = Field(default_factory=list)
    repeated_keywords: list[str] = Field(default_factory=list)
    missing_angles: list[str] = Field(default_factory=list)
    unique_video_angle: str = Field(min_length=1)
    hook_opportunities: list[str] = Field(default_factory=list)
    credibility_notes: list[str] = Field(default_factory=list)
    originality_score: int = Field(ge=0, le=100)


class TitleSource(Protocol):
    """Protocol for existing public title sources used by trend collection."""

    def fetch_titles(self) -> list[str]:
        raise NotImplementedError


class HackerNewsTitleSource(Protocol):
    def fetch_top_stories(self) -> list[str]:
        raise NotImplementedError


class NewsTitleSource(Protocol):
    def fetch_headlines(self) -> list[str]:
        raise NotImplementedError


class CompetitorAnalysisService:
    """Analyze public content titles to find original creator angles."""

    def __init__(
        self,
        reddit_service: TitleSource | None = None,
        hacker_news_service: HackerNewsTitleSource | None = None,
        news_api_service: NewsTitleSource | None = None,
        llm_service: "BaseLLMService | None" = None,
    ) -> None:
        self.reddit_service = reddit_service
        self.hacker_news_service = hacker_news_service
        self.news_api_service = news_api_service
        self.llm_service = llm_service

    def analyze(self, topic: str) -> CompetitorAnalysis:
        """Return content-gap analysis, always falling back instead of raising."""
        try:
            titles = self._fetch_competitor_titles(topic)
            if titles:
                return self._analyze_titles(topic=topic, titles=titles)
            logger.warning("No live competitor titles found for topic=%s; using LLM fallback", topic)
        except Exception:
            logger.exception("Live competitor analysis failed for topic=%s; using LLM fallback", topic)

        return self._fallback_analysis(topic)

    def _fetch_competitor_titles(self, topic: str) -> list[str]:
        titles: list[str] = []
        source_calls = (
            lambda: self.reddit_service.fetch_titles() if self.reddit_service else [],
            lambda: self.hacker_news_service.fetch_top_stories() if self.hacker_news_service else [],
            lambda: self.news_api_service.fetch_headlines() if self.news_api_service else [],
        )
        for fetch in source_calls:
            try:
                titles.extend(fetch())
            except Exception:
                logger.exception("Competitor title source failed for topic=%s", topic)

        topic_tokens = set(self._tokens(topic))
        ranked = sorted(
            self._dedupe(titles),
            key=lambda title: self._topic_overlap(title, topic_tokens),
            reverse=True,
        )
        relevant = [title for title in ranked if self._topic_overlap(title, topic_tokens) > 0]
        filler = [title for title in ranked if title not in relevant]
        return (relevant + filler)[:5]

    def _analyze_titles(self, topic: str, titles: list[str]) -> CompetitorAnalysis:
        tokens = [token for title in titles for token in self._tokens(title)]
        keyword_counts = Counter(tokens)
        repeated_keywords = [word for word, count in keyword_counts.most_common(8) if count > 1]
        common_angles = self._common_angles(titles)
        missing_angles = self._missing_angles(topic, common_angles, repeated_keywords)
        unique_angle = missing_angles[0] if missing_angles else f"Show the practical side of {topic} that most summaries skip."
        originality_score = max(55, min(95, 88 - len(repeated_keywords) * 3 + len(missing_angles) * 2))

        return CompetitorAnalysis(
            searched_topic=topic,
            competitor_titles=titles[:5],
            common_angles=common_angles,
            repeated_keywords=repeated_keywords,
            missing_angles=missing_angles,
            unique_video_angle=unique_angle,
            hook_opportunities=[
                f"Most videos talk about {repeated_keywords[0]}, but they miss this." if repeated_keywords else f"Most people explain {topic} the same way.",
                f"The overlooked part of {topic} is what happens next.",
                f"Here is the {topic} angle creators are not using yet.",
            ],
            credibility_notes=[
                "Use public source titles as directional signals, not verified facts.",
                "Verify statistics and official claims before scripting.",
            ],
            originality_score=originality_score,
        )

    def _fallback_analysis(self, topic: str) -> CompetitorAnalysis:
        try:
            if self.llm_service is not None:
                research = self.llm_service.research(topic=topic)
                return CompetitorAnalysis(
                    searched_topic=topic,
                    competitor_titles=[],
                    common_angles=[research.summary],
                    repeated_keywords=research.keywords[:5],
                    missing_angles=[research.video_angle],
                    unique_video_angle=research.video_angle,
                    hook_opportunities=research.hook_ideas,
                    credibility_notes=["Fallback generated from the configured local LLM research provider."],
                    originality_score=72,
                )
        except Exception:
            logger.exception("LLM competitor fallback failed for topic=%s; using static fallback", topic)

        return CompetitorAnalysis(
            searched_topic=topic,
            competitor_titles=[],
            common_angles=[f"General explanations of {topic}"],
            repeated_keywords=[topic],
            missing_angles=[f"A practical, viewer-first reason {topic} matters now."],
            unique_video_angle=f"Explain the overlooked practical impact of {topic} without hype.",
            hook_opportunities=[
                f"Most people are missing the practical side of {topic}.",
                f"{topic} is not just hype. Here is the useful part.",
                f"Before you ignore {topic}, watch this angle.",
            ],
            credibility_notes=["Live competitor analysis and LLM fallback were unavailable."],
            originality_score=65,
        )

    def _common_angles(self, titles: list[str]) -> list[str]:
        angles: list[str] = []
        patterns = {
            "tool list or roundup": r"\b(top|best|tools|apps|roundup)\b",
            "breaking news or announcement": r"\b(launch|announces|release|new|update)\b",
            "risk or controversy": r"\b(risk|problem|ban|lawsuit|warning|concern)\b",
            "productivity or business impact": r"\b(productivity|business|work|jobs|money)\b",
        }
        joined = " ".join(titles).lower()
        for label, pattern in patterns.items():
            if re.search(pattern, joined):
                angles.append(label)
        return angles or ["general explainer"]

    def _missing_angles(self, topic: str, common_angles: list[str], repeated_keywords: list[str]) -> list[str]:
        candidates = [
            f"What beginners should actually do with {topic} today.",
            f"The hidden tradeoff behind {topic}.",
            f"One practical example that makes {topic} easier to understand.",
        ]
        if "risk or controversy" not in common_angles:
            candidates.append(f"The real limitation of {topic} that hype videos skip.")
        if repeated_keywords:
            candidates.append(f"Move past '{repeated_keywords[0]}' and explain what changes for viewers.")
        return candidates[:4]

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
        }
        return [
            token
            for token in re.findall(r"[a-z0-9]+", text.lower())
            if len(token) > 2 and token not in stopwords
        ]

    def _topic_overlap(self, title: str, topic_tokens: set[str]) -> int:
        if not topic_tokens:
            return 0
        return len(set(self._tokens(title)) & topic_tokens)

    def _dedupe(self, titles: list[str]) -> list[str]:
        seen: set[str] = set()
        unique: list[str] = []
        for title in titles:
            normalized = re.sub(r"\s+", " ", title.strip().lower())
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique.append(title.strip())
        return unique
