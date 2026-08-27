from clips_lives_analyzer.candidates import merge_candidates, signal_proposals
from clips_lives_analyzer.config import AnalyzerConfig
from clips_lives_analyzer.models import Candidate, SignalPoint


def test_routine_low_activity_does_not_create_candidate():
    config = AnalyzerConfig()
    signals = [
        SignalPoint(
            time=float(index),
            motion=0.2,
            center_activity=0.2,
            killfeed_activity=0.1,
            audio_energy=0.3,
            audio_peak=0.1,
        )
        for index in range(100)
    ]
    assert signal_proposals(signals, 100, config) == []


def test_combined_combat_signals_create_usable_window():
    config = AnalyzerConfig()
    signals = [SignalPoint(time=float(index), motion=0.1, center_activity=0.1) for index in range(100)]
    signals[50] = SignalPoint(
        time=50,
        motion=0.95,
        center_activity=0.9,
        killfeed_activity=0.92,
        audio_energy=0.8,
        audio_peak=0.9,
    )
    candidates = signal_proposals(signals, 100, config)
    assert len(candidates) == 1
    assert candidates[0].start < 50 < candidates[0].end
    assert "killfeed" in candidates[0].source_signals
    assert candidates[0].end - candidates[0].start >= config.candidate_min_seconds


def test_same_event_heavily_overlapping_candidates_merge():
    config = AnalyzerConfig(candidate_merge_overlap_ratio=0.4, candidate_max_seconds=90)
    first = Candidate("a", 10, 50, ["fala"], description="item bizarro")
    second = Candidate("b", 30, 60, ["combate_visual"], description="payoff")
    merged = merge_candidates([first, second], 100, config)
    assert len(merged) == 1
    assert set(merged[0].source_signals) == {"fala", "combate_visual"}


def test_distinct_close_events_are_not_merged_only_by_proximity():
    config = AnalyzerConfig(candidate_merge_overlap_ratio=0.4, candidate_max_seconds=90)
    first = Candidate("a", 10, 40, ["combate_visual"], description="primeira play")
    second = Candidate("b", 36, 66, ["combate_visual"], description="segunda play")
    merged = merge_candidates([first, second], 100, config)
    assert len(merged) == 2
