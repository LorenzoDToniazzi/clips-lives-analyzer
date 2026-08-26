from pathlib import Path

from clips_lives_analyzer.config import AnalyzerConfig
from clips_lives_analyzer.editorial import EditorialAnalyzer
from clips_lives_analyzer.models import Candidate, TranscriptSegment


class FakeClient:
    def __init__(self, response):
        self.response = response

    def generate_json(self, **_kwargs):
        return self.response


class FakeStoryboards:
    def build(self, *_args, **_kwargs):
        return []


def response(decision: str, confidence: float):
    return {
        "decision": decision,
        "start": 20,
        "end": 34,
        "category": "Ciência",
        "what_happened": "Explicou o item estranho.",
        "why_good": "A decisão ensina e prepara um teste.",
        "evidence": ["fala explícita"],
        "confidence": confidence,
        "related_search_terms": [],
    }


def test_semantic_candidate_survives_uncertain_discard_in_coverage_mode(tmp_path: Path):
    config = AnalyzerConfig(analysis_profile="coverage")
    analyzer = EditorialAnalyzer(config, FakeClient(response("discard", 0.6)), {})
    analyzer.storyboards = FakeStoryboards()
    candidate = Candidate(
        "id",
        10,
        50,
        ["fala"],
        description="explicação de item",
        proposal_score=0.8,
    )
    result = analyzer.analyze(
        tmp_path / "live.mp4",
        candidate,
        [TranscriptSegment(18, 35, "comprei isso porque...")],
        tmp_path,
        cancelled=lambda: False,
    )
    assert result.keep is True
    assert result.grade == "C"


def test_confident_routine_discard_is_removed(tmp_path: Path):
    config = AnalyzerConfig(analysis_profile="coverage")
    analyzer = EditorialAnalyzer(config, FakeClient(response("discard", 0.95)), {})
    analyzer.storyboards = FakeStoryboards()
    candidate = Candidate("id", 10, 50, ["atividade_combinada"], proposal_score=0.5)
    result = analyzer.analyze(
        tmp_path / "live.mp4",
        candidate,
        [],
        tmp_path,
        cancelled=lambda: False,
    )
    assert result.keep is False
