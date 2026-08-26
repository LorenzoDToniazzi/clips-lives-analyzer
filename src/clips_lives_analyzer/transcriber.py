from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from clips_lives_analyzer.config import AnalyzerConfig
from clips_lives_analyzer.models import TranscriptSegment, TranscriptWord


INITIAL_PROMPT = (
    "Live brasileira de League of Legends. Vocabulário provável: build, item, runa, "
    "matchup, ciência, off-meta, X1, Arena, Draft Lab, Laboratório, kill, dive, "
    "gank, mid, top, jungle, ADC, suporte, flash, ignite, ultimate, stack, proc."
)


class Transcriber:
    def __init__(self, config: AnalyzerConfig):
        self.config = config

    @staticmethod
    def cuda_available() -> bool:
        try:
            import ctranslate2

            return ctranslate2.get_cuda_device_count() > 0
        except Exception:
            return False

    def _create_model(self, device: str) -> Any:
        from faster_whisper import WhisperModel

        compute_type = (
            self.config.whisper_gpu_compute_type
            if device == "cuda"
            else self.config.whisper_cpu_compute_type
        )
        return WhisperModel(
            self.config.whisper_model,
            device=device,
            compute_type=compute_type,
        )

    def transcribe(
        self,
        audio_path: Path,
        duration: float,
        *,
        progress: Callable[[float, str], None],
        cancelled: Callable[[], bool],
    ) -> tuple[list[TranscriptSegment], dict[str, Any]]:
        requested = self.config.whisper_device
        device = (
            "cuda"
            if requested == "cuda" or (requested == "auto" and self.cuda_available())
            else "cpu"
        )
        fallback_reason = None
        try:
            model = self._create_model(device)
        except Exception as exc:
            if device != "cuda" or requested == "cuda":
                raise
            fallback_reason = f"CUDA do Whisper indisponível ({exc}); usando CPU."
            progress(0, fallback_reason)
            device = "cpu"
            model = self._create_model(device)

        try:
            generator, info = model.transcribe(
                str(audio_path),
                language=None if self.config.language == "auto" else self.config.language,
                beam_size=5,
                word_timestamps=True,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 900},
                condition_on_previous_text=True,
                initial_prompt=INITIAL_PROMPT,
            )
            segments: list[TranscriptSegment] = []
            for segment in generator:
                if cancelled():
                    raise InterruptedError
                words = [
                    TranscriptWord(
                        start=float(word.start),
                        end=float(word.end),
                        text=str(word.word),
                        probability=(
                            float(word.probability)
                            if word.probability is not None
                            else None
                        ),
                    )
                    for word in (segment.words or [])
                ]
                item = TranscriptSegment(
                    start=float(segment.start),
                    end=float(segment.end),
                    text=str(segment.text).strip(),
                    words=words,
                )
                segments.append(item)
                progress(
                    min(1.0, item.end / max(duration, 1)),
                    f"Transcrevendo {item.end / 60:.1f} de {duration / 60:.1f} min",
                )
        except Exception as exc:
            if device != "cuda" or requested == "cuda":
                raise
            fallback_reason = f"Whisper falhou na GPU ({exc}); repetindo na CPU."
            progress(0, fallback_reason)
            device = "cpu"
            model = self._create_model(device)
            generator, info = model.transcribe(
                str(audio_path),
                language=None if self.config.language == "auto" else self.config.language,
                beam_size=5,
                word_timestamps=True,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 900},
                condition_on_previous_text=True,
                initial_prompt=INITIAL_PROMPT,
            )
            segments = []
            for segment in generator:
                if cancelled():
                    raise InterruptedError
                words = [
                    TranscriptWord(
                        start=float(word.start),
                        end=float(word.end),
                        text=str(word.word),
                        probability=(
                            float(word.probability)
                            if word.probability is not None
                            else None
                        ),
                    )
                    for word in (segment.words or [])
                ]
                segments.append(
                    TranscriptSegment(
                        start=float(segment.start),
                        end=float(segment.end),
                        text=str(segment.text).strip(),
                        words=words,
                    )
                )
                progress(min(1.0, float(segment.end) / max(duration, 1)), "Transcrevendo")

        metadata = {
            "language": info.language,
            "language_probability": float(info.language_probability),
            "duration": duration,
            "device": device,
            "model": self.config.whisper_model,
            "fallback_reason": fallback_reason,
        }
        return segments, metadata
