from __future__ import annotations

import json
import os
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

from live_splitter.models import MediaInfo
from live_splitter.utils import run_process


def _bundled_tool(name: str) -> str | None:
    executable = f"{name}.exe" if os.name == "nt" else name
    roots: list[Path] = []
    configured = os.environ.get("LIVE_SPLITTER_FFMPEG_DIR")
    if configured:
        roots.append(Path(configured))
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent)
        bundle_root = getattr(sys, "_MEIPASS", None)
        if bundle_root:
            roots.append(Path(bundle_root))
    for root in roots:
        candidate = root / executable
        if candidate.is_file():
            return str(candidate)
    return None


def require_tools() -> tuple[str, str]:
    ffmpeg = _bundled_tool("ffmpeg") or shutil.which("ffmpeg")
    ffprobe = _bundled_tool("ffprobe") or shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError(
            "FFmpeg e ffprobe não foram encontrados. Na versão portátil, mantenha "
            "todos os arquivos extraídos na mesma pasta. Na versão com código-fonte, "
            "execute INSTALAR.bat."
        )
    return ffmpeg, ffprobe


def probe_media(path: Path) -> MediaInfo:
    _ffmpeg, ffprobe = require_tools()
    result = run_process(
        [
            ffprobe,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        timeout_seconds=60,
    )
    payload = json.loads(result.stdout)
    streams = payload.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    if not video:
        raise ValueError(f"{path.name} não possui uma faixa de vídeo")
    format_data = payload.get("format", {})
    duration = float(format_data.get("duration") or video.get("duration") or 0)
    if duration <= 0:
        raise ValueError(f"Não foi possível descobrir a duração de {path.name}")
    return MediaInfo(
        duration=duration,
        size_bytes=path.stat().st_size,
        start_time=float(format_data.get("start_time") or 0),
        video_codec=str(video.get("codec_name") or "desconhecido"),
        audio_codec=str(audio.get("codec_name")) if audio else None,
        format_name=str(format_data.get("format_name") or "desconhecido"),
    )


def keyframe_at_or_before(path: Path, target: float) -> float:
    if target <= 0.05:
        return 0.0
    _ffmpeg, ffprobe = require_tools()
    for lookback in (30.0, 120.0, 600.0):
        interval_start = max(0.0, target - lookback)
        result = run_process(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-skip_frame",
                "nokey",
                "-read_intervals",
                f"{interval_start:.6f}%{target + 0.05:.6f}",
                "-show_entries",
                "frame=best_effort_timestamp_time",
                "-of",
                "csv=p=0",
                str(path),
            ],
            timeout_seconds=60,
        )
        values: list[float] = []
        for line in result.stdout.splitlines():
            raw = line.strip().strip(",")
            try:
                value = float(raw)
            except ValueError:
                continue
            if value <= target + 0.05:
                values.append(value)
        if values:
            return max(values)
    return max(0.0, target)


def copy_interval(
    source: Path,
    target: Path,
    *,
    start: float,
    duration: float,
    cancelled: Callable[[], bool],
) -> None:
    ffmpeg, _ffprobe = require_tools()
    run_process(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-ss",
            f"{start:.6f}",
            "-i",
            str(source),
            "-t",
            f"{duration:.6f}",
            "-map",
            "0",
            "-map_metadata",
            "0",
            "-map_chapters",
            "0",
            "-c",
            "copy",
            "-avoid_negative_ts",
            "make_zero",
            str(target),
        ],
        cancelled=cancelled,
    )
