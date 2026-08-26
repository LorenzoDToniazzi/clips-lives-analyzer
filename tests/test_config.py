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
    assert (tmp_path / "config.json").exists()


def test_invalid_scan_rate_is_rejected():
    with pytest.raises(ValueError):
        AnalyzerConfig(scan_fps=30).validate()
