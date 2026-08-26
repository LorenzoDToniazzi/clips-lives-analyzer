from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Stage(StrEnum):
    QUEUED = "queued"
    PREFLIGHT = "preflight"
    PROBE = "probe"
    AUDIO = "audio"
    TRANSCRIBE = "transcribe"
    SIGNALS = "signals"
    PROPOSALS = "proposals"
    DEEP_ANALYSIS = "deep_analysis"
    STORIES = "stories"
    REPORT = "report"
    COMPLETE = "complete"


@dataclass
class Job:
    id: str
    source_path: str
    fingerprint: str
    status: JobStatus
    stage: Stage
    progress: float
    priority: int
    created_at: str
    updated_at: str
    error: str | None = None
    result_path: str | None = None
    cancel_requested: bool = False

    @property
    def filename(self) -> str:
        return Path(self.source_path).name


@dataclass
class TranscriptWord:
    start: float
    end: float
    text: str
    probability: float | None = None


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str
    words: list[TranscriptWord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SignalPoint:
    time: float
    motion: float = 0.0
    scene_change: float = 0.0
    killfeed_activity: float = 0.0
    center_activity: float = 0.0
    hud_activity: float = 0.0
    audio_energy: float = 0.0
    audio_peak: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Candidate:
    id: str
    start: float
    end: float
    source_signals: list[str]
    category: str = "possível"
    description: str = ""
    evidence: list[str] = field(default_factory=list)
    proposal_score: float = 0.0
    keep: bool = True
    grade: str = "C"
    confidence: float = 0.5
    why_good: str = ""
    related_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Candidate":
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: value for key, value in data.items() if key in allowed})


@dataclass
class MediaInfo:
    path: str
    duration: float
    width: int
    height: int
    fps: float
    video_codec: str
    audio_codec: str | None
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
