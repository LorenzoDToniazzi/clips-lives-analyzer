from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from live_splitter.models import PartInfo, SplitResult
from live_splitter.runtime import data_directory
from live_splitter.utils import (
    ProcessCancelled,
    atomic_replace,
    format_timestamp,
    safe_name,
)

LOGGER = logging.getLogger(__name__)

DEFAULT_MODEL = "large-v3"
DEFAULT_LANGUAGE = "pt"
_CUDA_DLL_HANDLES: list[Any] = []


def _configure_cuda_dlls() -> None:
    """Expose the redistributable NVIDIA DLLs before CTranslate2 is imported."""
    if os.name != "nt":
        return
    roots: list[Path] = [Path(sys.executable).resolve().parent]
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        roots.append(Path(bundle_root))
    roots.extend(
        [
            Path(sys.prefix) / "Lib" / "site-packages",
            Path(__file__).resolve().parents[2],
        ]
    )
    seen: set[Path] = set()
    dll_directories: list[Path] = []
    for root in roots:
        for relative in (
            Path("nvidia") / "cublas" / "bin",
            Path("nvidia") / "cudnn" / "bin",
        ):
            candidate = (root / relative).resolve()
            if candidate.is_dir() and candidate not in seen:
                seen.add(candidate)
                dll_directories.append(candidate)
    if not dll_directories:
        return
    current_path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join(
        [*(str(item) for item in dll_directories), current_path]
    )
    add_directory = getattr(os, "add_dll_directory", None)
    if add_directory:
        for directory in dll_directories:
            _CUDA_DLL_HANDLES.append(add_directory(str(directory)))


@dataclass(frozen=True)
class TranscriptWord:
    start: float
    end: float
    text: str
    probability: float | None = None


@dataclass(frozen=True)
class TranscriptSegment:
    segment_id: str
    start: float
    end: float
    text: str
    words: tuple[TranscriptWord, ...] = ()


@dataclass(frozen=True)
class Transcript:
    source_file: str
    duration_seconds: float
    language: str
    language_probability: float | None
    model: str
    device: str
    compute_type: str
    generated_at: str
    segments: tuple[TranscriptSegment, ...]


@dataclass(frozen=True)
class TranscriptionArtifacts:
    master_txt: Path
    master_json: Path
    master_srt: Path
    part_files: tuple[dict[str, Any], ...]
    transcript: Transcript


def _precise_timestamp(seconds: float, *, srt: bool = False) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    separator = "," if srt else "."
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


def _atomic_write_text(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.part")
    try:
        temporary.write_text(content, encoding="utf-8")
        atomic_replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _serialize_segment(segment: TranscriptSegment) -> dict[str, Any]:
    return {
        "segment_id": segment.segment_id,
        "global_start": segment.start,
        "global_end": segment.end,
        "text": segment.text,
        "words": [asdict(word) for word in segment.words],
    }


class FasterWhisperTranscriber:
    """Lazy faster-whisper adapter with automatic CUDA to CPU fallback."""

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_MODEL,
        language: str = DEFAULT_LANGUAGE,
        model_directory: Path | None = None,
    ):
        self.model_name = model_name
        self.language = language
        self.model_directory = model_directory or data_directory() / "modelos-whisper"

    @staticmethod
    def require_runtime() -> str:
        _configure_cuda_dlls()
        try:
            import faster_whisper
        except ImportError as exc:
            raise RuntimeError(
                "O módulo de transcrição não foi encontrado. Baixe novamente a versão "
                "portátil completa ou execute INSTALAR.bat."
            ) from exc
        return str(getattr(faster_whisper, "__version__", "desconhecida"))

    def _run_attempt(
        self,
        source: Path,
        *,
        duration: float,
        device: str,
        compute_type: str,
        progress,
        cancelled,
    ) -> Transcript:
        from faster_whisper import WhisperModel

        if cancelled():
            raise ProcessCancelled
        self.model_directory.mkdir(parents=True, exist_ok=True)
        progress(
            0.01,
            f"Carregando {self.model_name} em {device.upper()} (primeiro uso pode baixar o modelo)",
        )
        model = WhisperModel(
            self.model_name,
            device=device,
            compute_type=compute_type,
            download_root=str(self.model_directory),
        )
        raw_segments, info = model.transcribe(
            str(source),
            language=self.language,
            task="transcribe",
            beam_size=5,
            vad_filter=True,
            word_timestamps=True,
            condition_on_previous_text=True,
        )
        segments: list[TranscriptSegment] = []
        for index, raw in enumerate(raw_segments, start=1):
            if cancelled():
                raise ProcessCancelled
            text = str(raw.text or "").strip()
            if not text:
                continue
            words = tuple(
                TranscriptWord(
                    start=max(0.0, float(word.start)),
                    end=min(duration, float(word.end)),
                    text=str(word.word),
                    probability=(
                        float(word.probability)
                        if word.probability is not None
                        else None
                    ),
                )
                for word in (raw.words or ())
                if word.start is not None and word.end is not None
            )
            start = max(0.0, float(raw.start))
            end = min(duration, float(raw.end))
            segments.append(
                TranscriptSegment(
                    segment_id=f"{safe_name(source.stem)}-segmento-{index:06d}",
                    start=start,
                    end=end,
                    text=text,
                    words=words,
                )
            )
            progress(
                min(0.99, end / max(duration, 1.0)),
                f"Transcrevendo {format_timestamp(end)} de {format_timestamp(duration)}",
            )
        detected_probability = getattr(info, "language_probability", None)
        return Transcript(
            source_file=source.name,
            duration_seconds=duration,
            language=self.language,
            language_probability=(
                float(detected_probability)
                if detected_probability is not None
                else None
            ),
            model=self.model_name,
            device=device,
            compute_type=compute_type,
            generated_at=datetime.now(UTC).isoformat(),
            segments=tuple(segments),
        )

    def transcribe(
        self,
        source: Path,
        *,
        duration: float,
        progress=None,
        cancelled=None,
    ) -> Transcript:
        self.require_runtime()
        progress = progress or (lambda _ratio, _message: None)
        cancelled = cancelled or (lambda: False)
        cuda_error: Exception | None = None
        try:
            return self._run_attempt(
                source,
                duration=duration,
                device="cuda",
                compute_type="float16",
                progress=progress,
                cancelled=cancelled,
            )
        except ProcessCancelled:
            raise
        except Exception as exc:
            cuda_error = exc
            LOGGER.warning(
                "CUDA indisponível para faster-whisper; usando CPU int8: %s",
                exc,
                exc_info=True,
            )
            progress(0.0, "GPU indisponível; continuando a transcrição pela CPU")
        try:
            return self._run_attempt(
                source,
                duration=duration,
                device="cpu",
                compute_type="int8",
                progress=progress,
                cancelled=cancelled,
            )
        except ProcessCancelled:
            raise
        except Exception as exc:
            raise RuntimeError(
                "Não foi possível iniciar a transcrição nem pela GPU nem pela CPU. "
                f"GPU: {cuda_error}. CPU: {exc}"
            ) from exc


def _part_segment(segment: TranscriptSegment, part: PartInfo) -> dict[str, Any] | None:
    intersection_start = max(segment.start, part.global_start)
    intersection_end = min(segment.end, part.global_end)
    if intersection_end <= intersection_start:
        return None
    selected_words = tuple(
        word
        for word in segment.words
        if word.end > part.global_start and word.start < part.global_end
    )
    if selected_words:
        global_start = max(part.global_start, selected_words[0].start)
        global_end = min(part.global_end, selected_words[-1].end)
        text = "".join(word.text for word in selected_words).strip()
    else:
        global_start = intersection_start
        global_end = intersection_end
        text = segment.text
    return {
        "segment_id": segment.segment_id,
        "global_start": global_start,
        "global_end": global_end,
        "original_global_start": segment.start,
        "original_global_end": segment.end,
        "local_start": max(0.0, global_start - part.global_start),
        "local_end": min(part.local_duration, global_end - part.global_start),
        "text": text,
        "words": [
            {
                "global_start": max(part.global_start, word.start),
                "global_end": min(part.global_end, word.end),
                "local_start": max(0.0, word.start - part.global_start),
                "local_end": min(part.local_duration, word.end - part.global_start),
                "text": word.text,
                "probability": word.probability,
            }
            for word in selected_words
        ],
    }


def write_transcription_files(
    result: SplitResult,
    transcript: Transcript,
) -> TranscriptionArtifacts:
    output_dir = result.output_dir
    title = result.source.stem
    master_txt = output_dir / f"TRANSCRICAO - {title}.txt"
    master_json = output_dir / f"TRANSCRICAO - {title}.json"
    master_srt = output_dir / f"TRANSCRICAO - {title}.srt"
    master_payload = {
        "live": title,
        "source_file": transcript.source_file,
        "duration_seconds": transcript.duration_seconds,
        "language": transcript.language,
        "language_probability": transcript.language_probability,
        "model": transcript.model,
        "device": transcript.device,
        "compute_type": transcript.compute_type,
        "generated_at": transcript.generated_at,
        "timeline": "global_da_live",
        "segments": [_serialize_segment(item) for item in transcript.segments],
    }
    _atomic_write_text(
        master_json,
        json.dumps(master_payload, ensure_ascii=False, indent=2),
    )
    master_lines = [
        f"TRANSCRIÇÃO COMPLETA: {title}",
        f"IDIOMA: {transcript.language}",
        f"MODELO: {transcript.model}",
        f"DISPOSITIVO: {transcript.device} ({transcript.compute_type})",
        "TIMELINE: tempo global da live",
        "",
    ]
    for segment in transcript.segments:
        master_lines.append(
            f"[LIVE {_precise_timestamp(segment.start)}-{_precise_timestamp(segment.end)}] "
            f"{segment.text}"
        )
    _atomic_write_text(master_txt, "\n".join(master_lines) + "\n")
    srt_lines: list[str] = []
    for index, segment in enumerate(transcript.segments, start=1):
        srt_lines.extend(
            [
                str(index),
                (
                    f"{_precise_timestamp(segment.start, srt=True)} --> "
                    f"{_precise_timestamp(segment.end, srt=True)}"
                ),
                segment.text,
                "",
            ]
        )
    _atomic_write_text(master_srt, "\n".join(srt_lines))

    part_files: list[dict[str, Any]] = []
    for part in result.parts:
        part_stem = Path(part.filename).stem
        txt_path = output_dir / f"{part_stem} - transcricao.txt"
        json_path = output_dir / f"{part_stem} - transcricao.json"
        mapped = [
            mapped_item
            for segment in transcript.segments
            if (mapped_item := _part_segment(segment, part)) is not None
        ]
        part_payload = {
            "live": title,
            "part_index": part.index,
            "video_file": part.filename,
            "global_start": part.global_start,
            "global_end": part.global_end,
            "local_duration": part.local_duration,
            "language": transcript.language,
            "model": transcript.model,
            "timeline_rule": "tempo_global = inicio_global_do_arquivo + tempo_local",
            "segments": mapped,
        }
        _atomic_write_text(
            json_path,
            json.dumps(part_payload, ensure_ascii=False, indent=2),
        )
        lines = [
            f"TRANSCRIÇÃO: {part.filename}",
            f"LIVE: {title}",
            f"INÍCIO GLOBAL DO ARQUIVO: {_precise_timestamp(part.global_start)}",
            f"FIM GLOBAL DO ARQUIVO: {_precise_timestamp(part.global_end)}",
            "REGRA: tempo da live = início global do arquivo + tempo local",
            "A sobreposição pode repetir segmentos de arquivos vizinhos.",
            "",
        ]
        for segment in mapped:
            lines.append(
                f"[ARQUIVO {_precise_timestamp(segment['local_start'])}-"
                f"{_precise_timestamp(segment['local_end'])} | "
                f"LIVE {_precise_timestamp(segment['global_start'])}-"
                f"{_precise_timestamp(segment['global_end'])} | "
                f"{segment['segment_id']}] {segment['text']}"
            )
        _atomic_write_text(txt_path, "\n".join(lines) + "\n")
        part_files.append(
            {
                "index": part.index,
                "video": part.filename,
                "transcript_txt": txt_path.name,
                "transcript_json": json_path.name,
            }
        )
    return TranscriptionArtifacts(
        master_txt=master_txt,
        master_json=master_json,
        master_srt=master_srt,
        part_files=tuple(part_files),
        transcript=transcript,
    )


def update_manifest_transcription(
    result: SplitResult,
    *,
    artifacts: TranscriptionArtifacts | None = None,
    error: str | None = None,
) -> None:
    payload = json.loads(result.manifest_json.read_text(encoding="utf-8"))
    if artifacts:
        transcript = artifacts.transcript
        metadata = {
            "status": "concluida",
            "language": transcript.language,
            "model": transcript.model,
            "device": transcript.device,
            "compute_type": transcript.compute_type,
            "generated_at": transcript.generated_at,
            "timeline": "global_da_live",
            "master_txt": artifacts.master_txt.name,
            "master_json": artifacts.master_json.name,
            "master_srt": artifacts.master_srt.name,
            "parts": list(artifacts.part_files),
        }
        txt_section = [
            "TRANSCRIÇÃO AUTOMÁTICA:",
            "  Status: concluída",
            f"  Idioma: {transcript.language}",
            f"  Modelo: {transcript.model}",
            f"  Dispositivo: {transcript.device} ({transcript.compute_type})",
            f"  Transcrição completa: {artifacts.master_txt.name}",
            "  Cada MP4 possui também um TXT e JSON com tempos locais e globais.",
        ]
    else:
        metadata = {"status": "falhou", "error": error or "erro desconhecido"}
        txt_section = [
            "TRANSCRIÇÃO AUTOMÁTICA:",
            "  Status: falhou",
            f"  Erro: {error or 'erro desconhecido'}",
            "  As partes de vídeo e os offsets do manifesto continuam válidos.",
        ]
    payload["transcription"] = metadata
    _atomic_write_text(
        result.manifest_json,
        json.dumps(payload, ensure_ascii=False, indent=2),
    )
    original = result.manifest_txt.read_text(encoding="utf-8")
    marker = "\nTRANSCRIÇÃO AUTOMÁTICA:\n"
    if marker in original:
        original = original.split(marker, 1)[0].rstrip()
    _atomic_write_text(
        result.manifest_txt,
        original.rstrip() + "\n\n" + "\n".join(txt_section) + "\n",
    )


def transcribe_split_result(
    result: SplitResult,
    *,
    transcriber: FasterWhisperTranscriber | None = None,
    progress=None,
    cancelled=None,
) -> TranscriptionArtifacts:
    transcriber = transcriber or FasterWhisperTranscriber()
    manifest_payload = json.loads(result.manifest_json.read_text(encoding="utf-8"))
    duration = float(manifest_payload["duration_seconds"])
    transcript = transcriber.transcribe(
        result.source,
        duration=duration,
        progress=progress,
        cancelled=cancelled,
    )
    artifacts = write_transcription_files(result, transcript)
    update_manifest_transcription(result, artifacts=artifacts)
    if progress:
        progress(1.0, "Transcrição e arquivos auxiliares concluídos")
    return artifacts
