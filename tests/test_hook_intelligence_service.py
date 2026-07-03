from services.hook_intelligence_service import HookIntelligenceService
from tests.test_script_agent import make_research_result


def test_successful_hook_generation_scores_and_ranks_candidates() -> None:
    service = HookIntelligenceService()
    research = make_research_result()

    selection = service.generate_hooks(research)

    assert selection.fallback_used is False
    assert 20 <= len(selection.candidates) <= 30
    assert selection.selected_hook == selection.candidates[0]
    assert selection.selected_hook.overall_score >= selection.candidates[-1].overall_score
    assert len(selection.top_hooks) == 3
    assert selection.selection_reason


def test_hook_selection_prefers_highest_scoring_hook() -> None:
    service = HookIntelligenceService()
    selection = service.generate_hooks(make_research_result())

    scores = [hook.overall_score for hook in selection.candidates]

    assert scores == sorted(scores, reverse=True)
    assert selection.selected_hook.overall_score == max(scores)


def test_hook_generation_fallback() -> None:
    class BrokenHookService(HookIntelligenceService):
        def _build_candidates(self, research_package):
            raise RuntimeError("hook failure")

    selection = BrokenHookService().generate_hooks(make_research_result())

    assert selection.fallback_used is True
    assert selection.selected_hook.type == "Curiosity"
    assert len(selection.candidates) == 1
