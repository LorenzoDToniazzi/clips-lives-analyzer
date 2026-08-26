from pathlib import Path

import pytest

from clips_lives_analyzer.config import AnalyzerConfig, load_config
from clips_lives_analyzer.paths import AppPaths


def make_paths(root: Path) -> AppPaths:
    return AppPaths(
        root=root,
        database=root / "queue.sqlite3",
        config=root / "config.json",
        jobs=root / "jobs",
        results=root / "results",
        logs=root / "logs",
    )


def test_default_config_is_created(tmp_path: Path):
    config = load_config(make_paths(tmp_path))
    assert config.analysis_profile == "coverage"
    assert config.vision_model == "qwen3-vl:8b"
    assert config.ollama_context == 8192
    assert config.storyboard_initial_frames == 9
    assert config.storyboard_deep_frames == 27
    assert config.whisper_allow_cpu_fallback is False
    assert (tmp_path / "config.json").exists()


def test_invalid_scan_rate_is_rejected():
    with pytest.raises(ValueError):
        AnalyzerConfig(scan_fps=30).validate()


def test_deep_storyboard_cannot_be_smaller_than_initial():
    with pytest.raises(ValueError):
        AnalyzerConfig(storyboard_initial_frames=18, storyboard_deep_frames=9).validate()
