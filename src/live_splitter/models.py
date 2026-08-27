from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SAFE_MAX_BYTES = 250_000_000
ABSOLUTE_MAX_BYTES = 256_000_000
MAX_DURATION_SECONDS = 20 * 60
OVERLAP_SECONDS = 30


@dataclass(frozen=True)
class SplitConfig:
    max_bytes: int = SAFE_MAX_BYTES
    max_duration_seconds: float = MAX_DURATION_SECONDS
    overlap_seconds: float = OVERLAP_SECONDS
    size_target_ratio: float = 0.96

    def validate(self) -> None:
        if not 100_000 <= self.max_bytes < ABSOLUTE_MAX_BYTES:
            raise ValueError("O limite deve ficar abaixo de 256 MB")
        if self.max_duration_seconds <= 1:
            raise ValueError("A duração máxima precisa ser maior que um segundo")
        if not 0 <= self.overlap_seconds < self.max_duration_seconds:
            raise ValueError("A sobreposição deve ser menor que a duração máxima")
        if not 0.5 <= self.size_target_ratio < 1:
            raise ValueError("A margem de tamanho deve ficar entre 0.5 e 1")


@dataclass(frozen=True)
class MediaInfo:
    duration: float
    size_bytes: int
    start_time: float
    video_codec: str
    audio_codec: str | None
    format_name: str


@dataclass(frozen=True)
class PartInfo:
    index: int
    filename: str
    global_start: float
    global_end: float
    local_duration: float
    size_bytes: int
    overlap_with_previous: float
    video_codec: str
    audio_codec: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SplitResult:
    source: Path
    output_dir: Path
    parts: list[PartInfo]
    manifest_txt: Path
    manifest_json: Path
