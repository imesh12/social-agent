from agents.research_agent import ResearchResult
from agents.script_agent import ScriptAgent
from tests.fake_llm import FakeLLMService


def test_script_agent_calls_review_script() -> None:
    llm = FakeLLMService(reviewed_script='Hook:\n"Stop scrolling. These tools matter."\n\nEnding:\n"Follow for more."')
    agent = ScriptAgent(llm_service=llm)

    result = agent.create_script(
        ResearchResult(
            topic="AI Tools",
            facts=["AI tools help creators move faster."],
        )
    )

    assert llm.review_called is True
    assert result.content == 'Hook:\n"Stop scrolling. These tools matter."\n\nEnding:\n"Follow for more."'


def test_script_agent_falls_back_to_draft_when_review_fails() -> None:
    llm = FakeLLMService(fail_review=True)
    agent = ScriptAgent(llm_service=llm)

    result = agent.create_script(
        ResearchResult(
            topic="AI Tools",
            facts=["AI tools help creators move faster."],
        )
    )

    assert llm.review_called is True
    assert "These AI tools are changing everything" in result.content
