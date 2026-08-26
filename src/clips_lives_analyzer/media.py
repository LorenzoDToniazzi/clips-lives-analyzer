from __future__ import annotations

import json
import shutil
import subprocess
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import numpy as np

from clips_lives_analyzer.models import MediaInfo


class ToolMissingError(RuntimeError):
    pass


def require_binary(name: str) -> str:
    binary = shutil.which(name)
    if binary:
        return binary
    raise ToolMissingError(
        f"{name} não foi encontrado. Rode INSTALAR.bat ou adicione-o ao PATH."
    )


def run_checked(
    command: list[str],
    *,
    cancelled: Callable[[], bool] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    while process.poll() is None:
        if cancelled and cancelled():
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            raise InterruptedError
        time.sleep(0.2)
    stdout, stderr = process.communicate()
    if process.returncode:
        details = stderr.strip().splitlines()[-12:]
        raise RuntimeError(
            f"Comando falhou ({process.returncode}): {' '.join(command[:4])}\n"
            + "\n".join(details)
        )
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def parse_rate(value: str | None) -> float:
    if not value or value == "0/0":
        return 0.0
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        return float(numerator) / max(float(denominator), 1.0)
    return float(value)


def probe_media(path: Path) -> MediaInfo:
    ffprobe = require_binary("ffprobe")
    result = run_checked(
        [
            ffprobe,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]
    )
    payload = json.loads(result.stdout)
    streams = payload.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if not video:
        raise ValueError(f"O arquivo não possui faixa de vídeo: {path.name}")
    duration = float(
        payload.get("format", {}).get("duration")
        or video.get("duration")
        or 0
    )
    if duration <= 0:
        raise ValueError(f"Não foi possível determinar a duração de {path.name}")
    return MediaInfo(
        path=str(path),
        duration=duration,
        width=int(video.get("width") or 0),
        height=int(video.get("height") or 0),
        fps=parse_rate(video.get("avg_frame_rate") or video.get("r_frame_rate")),
        video_codec=str(video.get("codec_name") or "unknown"),
        audio_codec=str(audio.get("codec_name")) if audio else None,
        size_bytes=path.stat().st_size,
    )


def extract_audio(
    source: Path,
    target: Path,
    cancelled: Callable[[], bool] | None = None,
) -> Path:
    ffmpeg = require_binary("ffmpeg")
    target.parent.mkdir(parents=True, exist_ok=True)
    run_checked(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(target),
        ],
        cancelled=cancelled,
    )
    return target


def iter_gray_frames(
    source: Path,
    *,
    fps: float,
    width: int,
    height: int,
    cancelled: Callable[[], bool] | None = None,
) -> Iterator[np.ndarray]:
    ffmpeg = require_binary("ffmpeg")
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-vf",
        (
            f"fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black"
        ),
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "pipe:1",
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    frame_size = width * height
    assert process.stdout is not None
    try:
        while True:
            if cancelled and cancelled():
                raise InterruptedError
            data = process.stdout.read(frame_size)
            if not data:
                break
            if len(data) != frame_size:
                raise RuntimeError("FFmpeg retornou um frame incompleto")
            yield np.frombuffer(data, dtype=np.uint8).reshape(height, width)
        return_code = process.wait()
        if return_code:
            assert process.stderr is not None
            error = process.stderr.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Falha ao ler frames: {error[-2000:]}")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()


def extract_frame(source: Path, timestamp: float, target: Path) -> Path:
    ffmpeg = require_binary("ffmpeg")
    target.parent.mkdir(parents=True, exist_ok=True)
    run_checked(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{max(0, timestamp):.3f}",
            "-i",
            str(source),
            "-frames:v",
            "1",
            "-vf",
            "scale=960:-2",
            "-q:v",
            "3",
            str(target),
        ]
    )
    return target
