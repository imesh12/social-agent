import time
from typing import Any

from pydantic import BaseModel, Field

from services.utils.logging import get_rotating_logger

hook_logger = get_rotating_logger("hook_intelligence", "hook.log")


class HookCandidate(BaseModel):
    """A scored short-form video hook candidate."""

    text: str = Field(min_length=1)
    type: str = Field(min_length=1)
    emotion: str = Field(min_length=1)
    curiosity_score: int = Field(ge=0, le=100)
    clarity_score: int = Field(ge=0, le=100)
    novelty_score: int = Field(ge=0, le=100)
    retention_score: int = Field(ge=0, le=100)
    overall_score: int = Field(ge=0, le=100)
    reasoning: str = Field(default="")


class HookSelection(BaseModel):
    """Selected hook plus ranked candidate context."""

    candidates: list[HookCandidate] = Field(min_length=1)
    selected_hook: HookCandidate
    selection_reason: str = Field(min_length=1)
    generation_time: float = Field(ge=0)
    fallback_used: bool = False

    @property
    def top_hooks(self) -> list[HookCandidate]:
        """Return the top three hooks by score."""
        return self.candidates[:3]


class HookIntelligenceService:
    """Generate, score, and rank hooks from verified research context."""

    hook_types = (
        "Curiosity",
        "Shock",
        "Question",
        "Contrarian",
        "Myth Busting",
        "Future Prediction",
        "List",
        "Statistic",
        "Story",
        "Warning",
        "Comparison",
        "Challenge",
    )

    def generate_hooks(self, research_package: Any) -> HookSelection:
        """Generate 20-30 deterministic hook candidates and select the best one."""
        started_at = time.perf_counter()
        topic = str(getattr(research_package, "topic", "this topic"))
        try:
            hooks = self._build_candidates(research_package)
            ranked = sorted(hooks, key=lambda hook: hook.overall_score, reverse=True)
            selection = HookSelection(
                candidates=ranked,
                selected_hook=ranked[0],
                selection_reason=self._selection_reason(ranked[0], research_package),
                generation_time=round(time.perf_counter() - started_at, 4),
                fallback_used=False,
            )
            self._log_selection(topic, selection)
            return selection
        except Exception:
            hook_logger.exception("Hook intelligence failed topic=%s; using fallback", topic)
            fallback = self._fallback_selection(topic, started_at)
            self._log_selection(topic, fallback)
            return fallback

    def _build_candidates(self, research_package: Any) -> list[HookCandidate]:
        topic = str(getattr(research_package, "topic", "this topic"))
        angle = self._angle(research_package)
        claims = self._verified_claims(research_package)
        keywords = list(getattr(research_package, "keywords", []) or [])
        missing_angles = []
        competitor_analysis = getattr(research_package, "competitor_analysis", None)
        if competitor_analysis is not None:
            missing_angles = list(getattr(competitor_analysis, "missing_angles", []) or [])

        base_claim = claims[0] if claims else str(getattr(research_package, "summary", angle))
        second_claim = claims[1] if len(claims) > 1 else str(getattr(research_package, "why_it_matters", angle))
        keyword = keywords[0] if keywords else topic
        missing = missing_angles[0] if missing_angles else angle

        templates = [
            ("Curiosity", "intrigue", f"Most people miss the real reason {topic} matters."),
            ("Curiosity", "intrigue", f"The overlooked part of {topic} is not what you think."),
            ("Shock", "surprise", f"{topic} is changing faster than creators realize."),
            ("Shock", "surprise", f"This simple {keyword} shift could surprise you."),
            ("Question", "curiosity", f"What if {topic} is useful for one reason everyone skips?"),
            ("Question", "curiosity", f"Why is everyone talking about {topic} right now?"),
            ("Contrarian", "skepticism", f"{topic} is not really about hype."),
            ("Contrarian", "skepticism", f"Stop watching generic {topic} lists for a second."),
            ("Myth Busting", "clarity", f"The biggest myth about {topic} is easy to miss."),
            ("Myth Busting", "clarity", f"{topic} will not help unless you understand this."),
            ("Future Prediction", "anticipation", f"The next phase of {topic} starts with one small change."),
            ("Future Prediction", "anticipation", f"In the near future, {topic} may feel less like a tool and more like a workflow."),
            ("List", "focus", f"Three quick things explain why {topic} keeps growing."),
            ("List", "focus", f"Here are three clues that {topic} is becoming practical."),
            ("Statistic", "credibility", f"Before you trust any {topic} statistic, check this first."),
            ("Statistic", "credibility", f"The useful number behind {topic} is the time it can save."),
            ("Story", "relatability", f"A creator using {topic} usually notices one thing first."),
            ("Story", "relatability", f"Imagine opening your workflow and letting {topic} handle the boring part."),
            ("Warning", "urgency", f"Do not use {topic} until you understand this tradeoff."),
            ("Warning", "urgency", f"One mistake makes {topic} feel useless."),
            ("Comparison", "contrast", f"{topic} is less like a shortcut and more like a second draft."),
            ("Comparison", "contrast", f"The difference between good and bad {topic} use is this."),
            ("Challenge", "motivation", f"Try using {topic} for one tiny task today."),
            ("Challenge", "motivation", f"If you think {topic} is just hype, test this workflow."),
            ("Curiosity", "intrigue", f"{missing}"),
            ("Story", "relatability", f"{base_claim} But the useful part comes next."),
            ("Comparison", "contrast", f"{second_claim} The trick is knowing what to automate."),
        ]
        candidates = [
            self._score_candidate(text=text, hook_type=hook_type, emotion=emotion, research_package=research_package)
            for hook_type, emotion, text in templates[:27]
        ]
        return candidates

    def _score_candidate(
        self,
        text: str,
        hook_type: str,
        emotion: str,
        research_package: Any,
    ) -> HookCandidate:
        competitor_analysis = getattr(research_package, "competitor_analysis", None)
        repeated_keywords = set(getattr(competitor_analysis, "repeated_keywords", []) or []) if competitor_analysis else set()
        unique_angle = str(getattr(competitor_analysis, "unique_video_angle", "") or "") if competitor_analysis else ""
        lower = text.lower()
        word_count = len(text.split())
        clarity = max(60, 100 - max(0, word_count - 14) * 4)
        curiosity = 78 + (8 if any(word in lower for word in ("why", "what", "miss", "overlooked", "this")) else 0)
        novelty = 75 + (10 if unique_angle and self._overlap(text, unique_angle) else 0)
        novelty -= sum(5 for keyword in repeated_keywords if str(keyword).lower() in lower)
        retention = 78 + (8 if hook_type in {"Curiosity", "Warning", "Contrarian", "Myth Busting"} else 0)
        emotion_score = 76 + (8 if emotion in {"intrigue", "surprise", "urgency"} else 0)
        overall = round((curiosity * 0.25) + (clarity * 0.2) + (novelty * 0.2) + (retention * 0.25) + (emotion_score * 0.1))
        return HookCandidate(
            text=text.strip(),
            type=hook_type,
            emotion=emotion,
            curiosity_score=self._clamp(curiosity),
            clarity_score=self._clamp(clarity),
            novelty_score=self._clamp(novelty),
            retention_score=self._clamp(retention),
            overall_score=self._clamp(overall),
            reasoning=f"{hook_type} hook scored for clarity, curiosity, originality, and retention.",
        )

    def _fallback_selection(self, topic: str, started_at: float) -> HookSelection:
        candidate = HookCandidate(
            text=f"Most people miss the practical side of {topic}.",
            type="Curiosity",
            emotion="intrigue",
            curiosity_score=75,
            clarity_score=85,
            novelty_score=70,
            retention_score=75,
            overall_score=76,
            reasoning="Fallback hook keeps the topic clear and curiosity-driven.",
        )
        return HookSelection(
            candidates=[candidate],
            selected_hook=candidate,
            selection_reason="Fallback selected a clear curiosity hook because hook generation failed.",
            generation_time=round(time.perf_counter() - started_at, 4),
            fallback_used=True,
        )

    def _verified_claims(self, research_package: Any) -> list[str]:
        verification = getattr(research_package, "fact_verification", None)
        if verification is not None and getattr(verification, "verified_claims", None):
            return list(verification.verified_claims)
        return list(getattr(research_package, "interesting_facts", []) or [])

    def _angle(self, research_package: Any) -> str:
        competitor_analysis = getattr(research_package, "competitor_analysis", None)
        if competitor_analysis is not None and getattr(competitor_analysis, "unique_video_angle", ""):
            return str(competitor_analysis.unique_video_angle)
        return str(getattr(research_package, "video_angle", "Explain one practical idea."))

    def _selection_reason(self, hook: HookCandidate, research_package: Any) -> str:
        angle = self._angle(research_package)
        return f"Selected the highest scoring {hook.type} hook because it supports the original angle: {angle}"

    def _log_selection(self, topic: str, selection: HookSelection) -> None:
        hook_logger.info(
            "Hook selection topic=%s selected_hook=%s score=%s top_3_hooks=%s generation_time=%s fallback_status=%s",
            topic,
            selection.selected_hook.text,
            selection.selected_hook.overall_score,
            [hook.text for hook in selection.top_hooks],
            selection.generation_time,
            selection.fallback_used,
        )

    def _overlap(self, left: str, right: str) -> bool:
        return bool(set(left.lower().split()) & set(right.lower().split()))

    def _clamp(self, value: int) -> int:
        return max(0, min(100, value))
