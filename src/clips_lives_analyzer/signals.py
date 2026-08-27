from __future__ import annotations

import wave
from collections.abc import Callable
from pathlib import Path

import numpy as np

from clips_lives_analyzer.config import AnalyzerConfig
from clips_lives_analyzer.media import iter_gray_frames
from clips_lives_analyzer.models import MediaInfo, SignalPoint


def _robust_normalize(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values
    low = float(np.percentile(values, 50))
    high = float(np.percentile(values, 96))
    if high <= low + 1e-9:
        return np.zeros_like(values, dtype=np.float64)
    return np.clip((values - low) / (high - low), 0, 1)


def _region_diff(current: np.ndarray, previous: np.ndarray, region: tuple[slice, slice]) -> float:
    current_region = current[region]
    previous_region = previous[region]
    return float(np.mean(np.abs(current_region.astype(np.int16) - previous_region.astype(np.int16))))


def scan_video(
    source: Path,
    media: MediaInfo,
    config: AnalyzerConfig,
    *,
    progress: Callable[[float, str], None],
    cancelled: Callable[[], bool],
) -> list[dict[str, float]]:
    width, height = config.scan_width, config.scan_height
    previous: np.ndarray | None = None
    raw: list[dict[str, float]] = []
    killfeed = (slice(0, int(height * 0.38)), slice(int(width * 0.70), width))
    center = (slice(int(height * 0.18), int(height * 0.82)), slice(int(width * 0.18), int(width * 0.82)))
    hud = (slice(int(height * 0.72), height), slice(0, width))
    for index, frame in enumerate(
        iter_gray_frames(
            source,
            fps=config.scan_fps,
            width=width,
            height=height,
            cancelled=cancelled,
        )
    ):
        timestamp = index / config.scan_fps
        if previous is not None:
            delta = np.abs(frame.astype(np.int16) - previous.astype(np.int16))
            raw.append(
                {
                    "time": timestamp,
                    "motion": float(np.mean(delta)),
                    "scene_change": float(np.mean(delta > 45)),
                    "killfeed_activity": _region_diff(frame, previous, killfeed),
                    "center_activity": _region_diff(frame, previous, center),
                    "hud_activity": _region_diff(frame, previous, hud),
                }
            )
        previous = frame.copy()
        if index % max(1, int(config.scan_fps * 30)) == 0:
            progress(
                min(1.0, timestamp / max(media.duration, 1)),
                f"Lendo vídeo {timestamp / 60:.1f} de {media.duration / 60:.1f} min",
            )
    if not raw:
        return raw
    for key in ("motion", "scene_change", "killfeed_activity", "center_activity", "hud_activity"):
        normalized = _robust_normalize(np.array([item[key] for item in raw]))
        for item, value in zip(raw, normalized, strict=True):
            item[key] = float(value)
    return raw


def scan_audio(audio_path: Path, bucket_seconds: float) -> list[dict[str, float]]:
    with wave.open(str(audio_path), "rb") as audio:
        frame_rate = audio.getframerate()
        channels = audio.getnchannels()
        sample_width = audio.getsampwidth()
        if sample_width != 2:
            raise ValueError("A análise de áudio espera PCM de 16 bits")
        frames_per_bucket = max(1, int(frame_rate * bucket_seconds))
        raw: list[tuple[float, float]] = []
        index = 0
        while True:
            data = audio.readframes(frames_per_bucket)
            if not data:
                break
            samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
            if channels > 1:
                samples = samples.reshape(-1, channels).mean(axis=1)
            rms = float(np.sqrt(np.mean(np.square(samples / 32768.0)) + 1e-12))
            raw.append((index * bucket_seconds, rms))
            index += 1
    energies = np.array([value for _, value in raw])
    normalized = _robust_normalize(energies)
    if normalized.size:
        kernel_size = min(21, len(normalized))
        kernel = np.ones(kernel_size) / kernel_size
        baseline = np.convolve(normalized, kernel, mode="same")
        peaks = np.clip(normalized - baseline, 0, 1)
    else:
        peaks = normalized
    return [
        {"time": time, "audio_energy": float(energy), "audio_peak": float(peak)}
        for (time, _), energy, peak in zip(raw, normalized, peaks, strict=True)
    ]


def combine_signals(
    video: list[dict[str, float]],
    audio: list[dict[str, float]],
    fps: float,
) -> list[SignalPoint]:
    if not video:
        return []
    audio_times = np.array([item["time"] for item in audio])
    result = []
    for item in video:
        if audio_times.size:
            audio_index = int(np.searchsorted(audio_times, item["time"]))
            audio_index = min(max(0, audio_index), len(audio) - 1)
            audio_item = audio[audio_index]
        else:
            audio_item = {"audio_energy": 0.0, "audio_peak": 0.0}
        result.append(
            SignalPoint(
                time=item["time"],
                motion=item["motion"],
                scene_change=item["scene_change"],
                killfeed_activity=item["killfeed_activity"],
                center_activity=item["center_activity"],
                hud_activity=item["hud_activity"],
                audio_energy=audio_item["audio_energy"],
                audio_peak=audio_item["audio_peak"],
            )
        )
    return result
