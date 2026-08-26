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
        compute_type = self.config.whisper_gpu_compute_type if device == "cuda" else self.config.whisper_cpu_compute_type
        return WhisperModel(self.config.whisper_model, device=device, compute_type=compute_type)

    def _select_device(self) -> tuple[str, str | None]:
        requested = self.config.whisper_device
        if requested == "cpu":
            return "cpu", None
        if requested == "cuda":
            return "cuda", None
        if self.cuda_available():
            return "cuda", None
        if self.config.whisper_allow_cpu_fallback:
            return "cpu", "CUDA do Whisper indisponível; fallback explícito para CPU habilitado."
        raise RuntimeError(
            "GPU/CUDA do Whisper não está disponível. O fallback automático para CPU está "
            "desativado para evitar processamento pesado sem aviso. Corrija CUDA/cuDNN ou "
            "ative whisper_allow_cpu_fallback manualmente no config.json."
        )

    @staticmethod
    def _segments_from_generator(
        generator: Any,
        *,
        duration: float,
        progress: Callable[[float, str], None],
        cancelled: Callable[[], bool],
    ) -> list[TranscriptSegment]:
        segments: list[TranscriptSegment] = []
        for segment in generator:
            if cancelled():
                raise InterruptedError
            words = [
                TranscriptWord(
                    start=float(word.start),
                    end=float(word.end),
                    text=str(word.word),
                    probability=float(word.probability) if word.probability is not None else None,
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
        return segments

    def _run_model(
        self,
        model: Any,
        audio_path: Path,
        duration: float,
        *,
        progress: Callable[[float, str], None],
        cancelled: Callable[[], bool],
    ) -> tuple[list[TranscriptSegment], Any]:
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
        return (
            self._segments_from_generator(
                generator,
                duration=duration,
                progress=progress,
                cancelled=cancelled,
            ),
            info,
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
        device, fallback_reason = self._select_device()
        if fallback_reason:
            progress(0, fallback_reason)
        try:
            model = self._create_model(device)
            segments, info = self._run_model(
                model,
                audio_path,
                duration,
                progress=progress,
                cancelled=cancelled,
            )
        except Exception as exc:
            can_fallback = (
                device == "cuda"
                and requested == "auto"
                and self.config.whisper_allow_cpu_fallback
            )
            if not can_fallback:
                if device == "cuda":
                    raise RuntimeError(
                        "O Whisper falhou ao executar na GPU. O fallback automático para CPU "
                        "está desativado para não consumir o processador sem aviso. Verifique "
                        "CUDA 12/cuBLAS/cuDNN 9 e rode o diagnóstico novamente."
                    ) from exc
                raise
            fallback_reason = f"Whisper falhou na GPU ({exc}); fallback para CPU foi autorizado."
            progress(0, fallback_reason)
            device = "cpu"
            model = self._create_model(device)
            segments, info = self._run_model(
                model,
                audio_path,
                duration,
                progress=progress,
                cancelled=cancelled,
            )

        metadata = {
            "language": info.language,
            "language_probability": float(info.language_probability),
            "duration": duration,
            "device": device,
            "model": self.config.whisper_model,
            "fallback_reason": fallback_reason,
        }
        return segments, metadata
