from pathlib import Path

from clips_lives_analyzer.config import AnalyzerConfig
from clips_lives_analyzer.editorial import EditorialAnalyzer
from clips_lives_analyzer.models import Candidate, TranscriptSegment


class FakeClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    def generate_json(self, **_kwargs):
        index = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return self.responses[index]


class FakeStoryboards:
    def __init__(self):
        self.frame_counts = []

    def build(self, *_args, frame_count=None, **_kwargs):
        self.frame_counts.append(frame_count)
        return []


def response(decision: str, confidence: float, *, potential: str = "sim", evidence: bool = True):
    return {
        "content_potential": potential,
        "decision": decision,
        "start": 20,
        "end": 34,
        "category": "ciencia_build",
        "what_happened": "Explicou o item estranho.",
        "why_candidate": "A decisão ensina e prepara um teste.",
        "routine_difference": "Existe uma hipótese concreta, não é apenas farming.",
        "evidence": (
            [{"time": 24, "type": "speech", "observation": "explica o motivo do item"}]
            if evidence
            else []
        ),
        "context_note": "Pode ter payoff posterior.",
        "confidence": confidence,
        "related_search_terms": ["item", "funcionou"],
    }


def test_semantic_candidate_survives_uncertain_discard_in_coverage_mode(tmp_path: Path):
    config = AnalyzerConfig(analysis_profile="coverage")
    client = FakeClient(
        response("discard", 0.6, potential="incerto"),
        response("discard", 0.7, potential="incerto"),
    )
    analyzer = EditorialAnalyzer(config, client, {})
    analyzer.storyboards = FakeStoryboards()
    candidate = Candidate("id", 10, 50, ["fala"], description="explicação de item", proposal_score=0.8)
    result = analyzer.analyze(
        tmp_path / "live.mp4",
        candidate,
        [TranscriptSegment(18, 35, "comprei isso porque...")],
        tmp_path,
        cancelled=lambda: False,
    )
    assert result.keep is True
    assert result.grade == "C"
    assert client.calls == 2


def test_confident_routine_discard_is_removed_without_dense_pass(tmp_path: Path):
    config = AnalyzerConfig(analysis_profile="coverage")
    client = FakeClient(response("discard", 0.95, potential="nao", evidence=False))
    analyzer = EditorialAnalyzer(config, client, {})
    storyboards = FakeStoryboards()
    analyzer.storyboards = storyboards
    candidate = Candidate("id", 10, 50, ["atividade_combinada"], proposal_score=0.5)
    result = analyzer.analyze(tmp_path / "live.mp4", candidate, [], tmp_path, cancelled=lambda: False)
    assert result.keep is False
    assert client.calls == 1
    assert storyboards.frame_counts == [config.storyboard_initial_frames]


def test_c_candidate_gets_dense_visual_review(tmp_path: Path):
    config = AnalyzerConfig()
    client = FakeClient(response("C", 0.65), response("B", 0.88))
    analyzer = EditorialAnalyzer(config, client, {})
    storyboards = FakeStoryboards()
    analyzer.storyboards = storyboards
    candidate = Candidate("id", 10, 50, ["fala"], description="ciência", proposal_score=0.8)
    result = analyzer.analyze(
        tmp_path / "live.mp4",
        candidate,
        [TranscriptSegment(18, 35, "isso deveria funcionar por causa de...")],
        tmp_path,
        cancelled=lambda: False,
    )
    assert result.keep is True
    assert result.grade == "B"
    assert storyboards.frame_counts == [config.storyboard_initial_frames, config.storyboard_deep_frames]
