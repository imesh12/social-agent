from services.llm.base_llm_service import BaseLLMService, LLMResearchResult, LLMSEOResult


class FakeLLMService(BaseLLMService):
    def __init__(self, reviewed_script: str | None = None, fail_review: bool = False) -> None:
        self.reviewed_script = reviewed_script
        self.fail_review = fail_review
        self.review_called = False

    def research(self, topic: str) -> LLMResearchResult:
        return LLMResearchResult(
            facts=[
                "AI productivity tools are being adopted by creators and small businesses.",
                "Automation features help users write, edit, summarize, and repurpose content.",
                "Short-form videos work well when they include clear examples.",
            ]
        )

    def generate_script(self, topic: str, facts: list[str]) -> str:
        return (
            'Hook:\n"These AI tools are changing everything."\n\n'
            'Body:\n"Three tools are becoming incredibly popular because they save time."\n\n'
            'Ending:\n"Which one would you try?"'
        )

    def review_script(self, script: str) -> str:
        self.review_called = True
        if self.fail_review:
            raise RuntimeError("review failed")
        return self.reviewed_script or script

    def generate_seo(self, script_text: str) -> LLMSEOResult:
        return LLMSEOResult(
            title="Top 3 AI Tools You Need In 2026 #shorts",
            description="Discover AI tools changing productivity.",
            tags=["AI", "ChatGPT", "Technology"],
            hashtags="#ai #shorts #technology",
        )
