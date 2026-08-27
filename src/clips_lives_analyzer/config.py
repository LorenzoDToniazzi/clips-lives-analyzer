from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from importlib.resources import files
from pathlib import Path
from typing import Any

from clips_lives_analyzer.paths import AppPaths


@dataclass
class AnalyzerConfig:
    analysis_profile: str = "coverage"
    language: str = "pt"
    whisper_model: str = "turbo"
    whisper_device: str = "auto"
    whisper_gpu_compute_type: str = "int8_float16"
    whisper_cpu_compute_type: str = "int8"
    whisper_allow_cpu_fallback: bool = False
    whisper_startup_timeout_seconds: int = 180
    whisper_inactivity_timeout_seconds: int = 180
    ollama_url: str = "http://127.0.0.1:11434"
    text_model: str = "qwen3-vl:8b"
    vision_model: str = "qwen3-vl:8b"
    scan_fps: float = 2.0
    scan_width: int = 320
    scan_height: int = 180
    transcript_chunk_seconds: int = 600
    transcript_overlap_seconds: int = 35
    candidate_pre_seconds: int = 14
    candidate_post_seconds: int = 18
    candidate_min_seconds: int = 18
    candidate_max_seconds: int = 115
    candidate_merge_overlap_ratio: float = 0.40
    story_max_gap_seconds: int = 7200
    storyboard_initial_frames: int = 9
    storyboard_deep_frames: int = 27
    storyboard_columns: int = 3
    ollama_context: int = 8192
    ollama_story_context: int = 16384
    ollama_timeout_seconds: int = 900
    cleanup_temporary_files: bool = True
    keep_internal_analysis: bool = True

    def validate(self) -> None:
        if self.analysis_profile not in {"coverage", "balanced"}:
            raise ValueError("analysis_profile deve ser 'coverage' ou 'balanced'")
        if not 0.25 <= self.scan_fps <= 5:
            raise ValueError("scan_fps deve ficar entre 0.25 e 5")
        if self.candidate_min_seconds >= self.candidate_max_seconds:
            raise ValueError("candidate_min_seconds deve ser menor que candidate_max_seconds")
        if not 0 < self.candidate_merge_overlap_ratio <= 1:
            raise ValueError("candidate_merge_overlap_ratio deve ficar entre 0 e 1")
        if self.storyboard_initial_frames < 3:
            raise ValueError("storyboard_initial_frames deve ser pelo menos 3")
        if self.storyboard_deep_frames < self.storyboard_initial_frames:
            raise ValueError(
                "storyboard_deep_frames deve ser maior ou igual a storyboard_initial_frames"
            )
        if self.ollama_context < 4096:
            raise ValueError("ollama_context deve ser pelo menos 4096")
        if self.ollama_story_context < self.ollama_context:
            raise ValueError("ollama_story_context deve ser maior ou igual a ollama_context")
        if self.whisper_startup_timeout_seconds < 30:
            raise ValueError("whisper_startup_timeout_seconds deve ser pelo menos 30")
        if self.whisper_inactivity_timeout_seconds < 30:
            raise ValueError("whisper_inactivity_timeout_seconds deve ser pelo menos 30")

    def save(self, path: Path) -> None:
        self.validate()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "AnalyzerConfig":
        allowed = {field.name for field in fields(cls)}
        config = cls(**{key: value for key, value in data.items() if key in allowed})
        config.validate()
        return config


def bundled_json(name: str) -> dict[str, Any]:
    resource = files("clips_lives_analyzer").joinpath("resources", name)
    return json.loads(resource.read_text(encoding="utf-8"))


def load_config(paths: AppPaths | None = None) -> AnalyzerConfig:
    paths = paths or AppPaths.default()
    paths.ensure()
    defaults = bundled_json("default_config.json")
    if paths.config.exists():
        overrides = json.loads(paths.config.read_text(encoding="utf-8"))
        defaults.update(overrides)
    config = AnalyzerConfig.from_mapping(defaults)
    if not paths.config.exists():
        config.save(paths.config)
    return config


def load_editorial_rules() -> dict[str, Any]:
    return bundled_json("editorial_rules.json")
