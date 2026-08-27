from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from live_splitter.manifest import write_manifests
from live_splitter.media import copy_interval, keyframe_at_or_before, probe_media
from live_splitter.models import PartInfo, SplitConfig, SplitResult
from live_splitter.utils import (
    VIDEO_EXTENSIONS,
    ProcessCancelled,
    atomic_replace,
    format_timestamp,
    safe_name,
    unique_directory,
)

ProgressCallback = Callable[[float, str], None]


class VodSplitter:
    def __init__(self, config: SplitConfig | None = None):
        self.config = config or SplitConfig()
        self.config.validate()

    def _initial_duration(
        self, remaining: float, average_bytes_per_second: float
    ) -> float:
        size_limited = (
            self.config.max_bytes
            * self.config.size_target_ratio
            / max(average_bytes_per_second, 1)
        )
        return max(1.0, min(remaining, self.config.max_duration_seconds, size_limited))

    def _create_part(
        self,
        source: Path,
        temporary: Path,
        *,
        start: float,
        requested_duration: float,
        remaining: float,
        cancelled: Callable[[], bool],
    ) -> tuple[float, int]:
        duration = min(requested_duration, remaining)
        attempts = 0
        while True:
            if cancelled():
                raise ProcessCancelled
            attempts += 1
            temporary.unlink(missing_ok=True)
            copy_interval(
                source,
                temporary,
                start=start,
                duration=duration,
                cancelled=cancelled,
            )
            size = temporary.stat().st_size
            part_media = probe_media(temporary)
            within_size = size < self.config.max_bytes
            within_duration = part_media.duration <= self.config.max_duration_seconds
            if within_size and within_duration:
                return part_media.duration, size
            if attempts >= 8:
                raise RuntimeError(
                    "Não foi possível deixar uma parte abaixo de 256 MB sem recodificar. "
                    "O arquivo pode possuir um keyframe anormalmente grande."
                )
            size_ratio = self.config.max_bytes / max(size, 1)
            new_duration = duration * min(size_ratio * 0.94, 1.0)
            if not within_duration:
                duration_excess = part_media.duration - self.config.max_duration_seconds
                new_duration = min(new_duration, duration - duration_excess - 0.25)
            if (
                new_duration >= duration - 0.2
                or new_duration <= self.config.overlap_seconds + 1
            ):
                raise RuntimeError(
                    "Uma região do vídeo é grande demais para o limite de 256 MB sem "
                    "recodificação."
                )
            duration = new_duration

    def split(
        self,
        source: Path,
        destination_root: Path,
        *,
        progress: ProgressCallback | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> SplitResult:
        source = source.resolve(strict=True)
        destination_root = destination_root.resolve()
        progress = progress or (lambda _ratio, _message: None)
        cancelled = cancelled or (lambda: False)
        if source.suffix.lower() not in VIDEO_EXTENSIONS:
            raise ValueError(
                f"Formato não suportado: {source.suffix or 'sem extensão'}"
            )
        if source.parent == destination_root:
            destination_root = destination_root / "Lives picotadas"
        destination_root.mkdir(parents=True, exist_ok=True)

        progress(0.0, f"Lendo {source.name}")
        media = probe_media(source)
        average_bytes_per_second = media.size_bytes / max(media.duration, 1)
        estimated_part_duration = self._initial_duration(
            media.duration,
            average_bytes_per_second,
        )
        advance_per_part = max(
            1.0,
            estimated_part_duration - self.config.overlap_seconds,
        )
        overlap_multiplier = estimated_part_duration / advance_per_part
        required_space = int(media.size_bytes * overlap_multiplier * 1.10)
        free_space = shutil.disk_usage(destination_root).free
        if free_space < required_space:
            raise RuntimeError(
                "Espaço insuficiente na pasta de saída. "
                f"Necessário aproximadamente {required_space / 1_000_000_000:.1f} GB; "
                f"disponível {free_space / 1_000_000_000:.1f} GB."
            )
        output_dir = unique_directory(destination_root, source.stem)
        output_dir.mkdir(parents=True, exist_ok=False)

        parts: list[PartInfo] = []
        current_start = 0.0
        previous_end = 0.0
        suffix = source.suffix.lower()
        base_name = safe_name(source.stem)
        try:
            while current_start < media.duration - 0.25:
                if cancelled():
                    raise ProcessCancelled
                index = len(parts) + 1
                remaining = media.duration - current_start
                requested_duration = self._initial_duration(
                    remaining,
                    average_bytes_per_second,
                )
                filename = f"{base_name} - arquivo {index:03d}{suffix}"
                final_path = output_dir / filename
                temporary = (
                    output_dir / f".{base_name} - arquivo {index:03d}.part{suffix}"
                )
                progress(
                    min(0.99, current_start / media.duration),
                    f"Criando arquivo {index:03d} a partir de {format_timestamp(current_start)}",
                )
                local_duration, size = self._create_part(
                    source,
                    temporary,
                    start=current_start,
                    requested_duration=requested_duration,
                    remaining=remaining,
                    cancelled=cancelled,
                )
                atomic_replace(temporary, final_path)
                global_end = min(media.duration, current_start + local_duration)
                part_media = probe_media(final_path)
                if part_media.video_codec != media.video_codec:
                    raise RuntimeError("O codec do vídeo mudou durante o corte")
                if part_media.audio_codec != media.audio_codec:
                    raise RuntimeError("O codec do áudio mudou durante o corte")
                overlap = max(0.0, previous_end - current_start) if parts else 0.0
                parts.append(
                    PartInfo(
                        index=index,
                        filename=filename,
                        global_start=current_start,
                        global_end=global_end,
                        local_duration=local_duration,
                        size_bytes=size,
                        overlap_with_previous=overlap,
                        video_codec=part_media.video_codec,
                        audio_codec=part_media.audio_codec,
                    )
                )
                previous_end = global_end
                if global_end >= media.duration - 0.25:
                    break
                desired_next = max(0.0, global_end - self.config.overlap_seconds)
                next_start = keyframe_at_or_before(source, desired_next)
                if next_start <= current_start + 0.5:
                    raise RuntimeError(
                        "O vídeo não possui keyframes suficientes para avançar"
                    )
                current_start = next_start

            manifest_txt, manifest_json = write_manifests(
                output_dir,
                source,
                media,
                parts,
            )
            progress(1.0, f"Concluído: {len(parts)} arquivos")
            return SplitResult(
                source=source,
                output_dir=output_dir,
                parts=parts,
                manifest_txt=manifest_txt,
                manifest_json=manifest_json,
            )
        except Exception:
            for temporary in output_dir.glob(".*.part.*"):
                temporary.unlink(missing_ok=True)
            raise
