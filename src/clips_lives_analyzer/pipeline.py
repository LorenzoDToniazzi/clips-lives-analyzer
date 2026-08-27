from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from clips_lives_analyzer.candidates import merge_candidates, semantic_proposals, signal_proposals
from clips_lives_analyzer.config import AnalyzerConfig, load_editorial_rules
from clips_lives_analyzer.editorial import EditorialAnalyzer
from clips_lives_analyzer.media import extract_audio, probe_media, require_binary
from clips_lives_analyzer.models import (
    Candidate,
    Job,
    MediaInfo,
    SignalPoint,
    Stage,
    TranscriptSegment,
    TranscriptWord,
)
from clips_lives_analyzer.ollama import OllamaClient
from clips_lives_analyzer.paths import AppPaths
from clips_lives_analyzer.report import write_report
from clips_lives_analyzer.signals import combine_signals, scan_audio, scan_video
from clips_lives_analyzer.story_builder import StoryBuilder
from clips_lives_analyzer.transcriber import Transcriber
from clips_lives_analyzer.utils import atomic_write_json, fingerprint_file, read_json


class AnalyzerPipeline:
    def __init__(self, paths: AppPaths, config: AnalyzerConfig):
        self.paths = paths
        self.config = config
        self.paths.ensure()
        self.client = OllamaClient(config)
        self.rules = load_editorial_rules()

    @staticmethod
    def _media(data: dict[str, Any]) -> MediaInfo:
        return MediaInfo(**data)

    @staticmethod
    def _transcript(data: list[dict[str, Any]]) -> list[TranscriptSegment]:
        return [
            TranscriptSegment(
                start=float(item["start"]),
                end=float(item["end"]),
                text=str(item["text"]),
                words=[TranscriptWord(**word) for word in item.get("words", [])],
            )
            for item in data
        ]

    @staticmethod
    def _signals(data: list[dict[str, Any]]) -> list[SignalPoint]:
        return [SignalPoint(**item) for item in data]

    @staticmethod
    def _candidates(data: list[dict[str, Any]]) -> list[Candidate]:
        return [Candidate.from_dict(item) for item in data]

    def process(
        self,
        job: Job,
        progress: Callable[[Stage, float, str], None],
        cancelled: Callable[[], bool],
    ) -> Path:
        source = Path(job.source_path)
        work_dir = self.paths.jobs / job.id
        work_dir.mkdir(parents=True, exist_ok=True)
        result_dir = self.paths.results / f"{source.stem}-{job.id[:8]}"
        metadata: dict[str, Any] = {}

        def checkpoint(stage: Stage, value: float, message: str) -> None:
            if cancelled():
                raise InterruptedError
            progress(stage, value, message)

        checkpoint(Stage.PREFLIGHT, 1, "Verificando dependências locais")
        require_binary("ffmpeg")
        require_binary("ffprobe")
        if not source.exists():
            raise FileNotFoundError(f"O VOD não existe mais: {source}")
        if fingerprint_file(source) != job.fingerprint:
            raise RuntimeError(
                "O arquivo mudou desde que entrou na fila. Remova e adicione novamente."
            )
        metadata["ollama_version"] = self.client.version()
        self.client.require_models()
        checkpoint(Stage.PREFLIGHT, 2, "Dependências verificadas")

        media_path = work_dir / "media.json"
        media_data = read_json(media_path)
        if media_data:
            media = self._media(media_data)
        else:
            media = probe_media(source)
            atomic_write_json(media_path, media.to_dict())
        checkpoint(Stage.PROBE, 4, f"VOD mapeado: {media.duration / 60:.1f} minutos")

        audio_path = work_dir / "audio.wav"
        if not audio_path.exists() or audio_path.stat().st_size < 44:
            checkpoint(Stage.AUDIO, 5, "Extraindo áudio")
            extract_audio(source, audio_path, cancelled=cancelled)
        checkpoint(Stage.AUDIO, 8, "Áudio preparado")

        transcript_path = work_dir / "transcript.json"
        transcript_data = read_json(transcript_path)
        if transcript_data:
            transcript = self._transcript(transcript_data["segments"])
            metadata["transcription"] = transcript_data.get("metadata", {})
        else:
            transcriber = Transcriber(self.config)
            last_percent = -1

            def transcription_progress(ratio: float, message: str) -> None:
                nonlocal last_percent
                percent = int(ratio * 100)
                if percent != last_percent:
                    last_percent = percent
                    checkpoint(Stage.TRANSCRIBE, 8 + ratio * 30, message)

            transcript, transcription_metadata = transcriber.transcribe(
                audio_path,
                media.duration,
                progress=transcription_progress,
                cancelled=cancelled,
            )
            metadata["transcription"] = transcription_metadata
            atomic_write_json(
                transcript_path,
                {
                    "metadata": transcription_metadata,
                    "segments": [item.to_dict() for item in transcript],
                },
            )
        checkpoint(Stage.TRANSCRIBE, 38, "Transcrição concluída")

        signals_path = work_dir / "signals.json"
        signals_data = read_json(signals_path)
        if signals_data:
            signals = self._signals(signals_data)
        else:
            video_signals = scan_video(
                source,
                media,
                self.config,
                progress=lambda ratio, message: checkpoint(
                    Stage.SIGNALS, 38 + ratio * 14, message
                ),
                cancelled=cancelled,
            )
            audio_signals = scan_audio(audio_path, 1 / self.config.scan_fps)
            signals = combine_signals(video_signals, audio_signals, self.config.scan_fps)
            atomic_write_json(signals_path, [item.to_dict() for item in signals])
        checkpoint(Stage.SIGNALS, 53, "Leitura contínua de áudio e vídeo concluída")

        proposals_path = work_dir / "proposals.json"
        proposals_data = read_json(proposals_path)
        if proposals_data:
            proposals = self._candidates(proposals_data)
        else:
            semantic = semantic_proposals(
                self.client,
                self.config,
                transcript,
                media.duration,
                self.rules,
                progress=lambda ratio, message: checkpoint(
                    Stage.PROPOSALS, 53 + ratio * 10, message
                ),
                cancelled=cancelled,
            )
            visual = signal_proposals(signals, media.duration, self.config)
            proposals = merge_candidates(semantic + visual, media.duration, self.config)
            atomic_write_json(proposals_path, [item.to_dict() for item in proposals])
        checkpoint(Stage.PROPOSALS, 64, f"{len(proposals)} janelas reais separadas para inspeção")

        deep_path = work_dir / "deep_analysis.json"
        deep_data = read_json(deep_path, [])
        analyzed_by_id = {
            item["id"]: Candidate.from_dict(item)
            for item in deep_data
            if item.get("id")
        }
        editorial = EditorialAnalyzer(self.config, self.client, self.rules)
        analyzed: list[Candidate] = []
        for index, candidate in enumerate(proposals):
            if cancelled():
                raise InterruptedError
            if candidate.id in analyzed_by_id:
                result = analyzed_by_id[candidate.id]
            else:
                result = editorial.analyze(
                    source,
                    candidate,
                    transcript,
                    work_dir,
                    cancelled=cancelled,
                )
                analyzed_by_id[result.id] = result
                atomic_write_json(
                    deep_path,
                    [item.to_dict() for item in analyzed_by_id.values()],
                )
            analyzed.append(result)
            checkpoint(
                Stage.DEEP_ANALYSIS,
                64 + 29 * ((index + 1) / max(len(proposals), 1)),
                f"Inspeção editorial {index + 1} de {len(proposals)}",
            )
        checkpoint(
            Stage.DEEP_ANALYSIS,
            93,
            f"{sum(item.keep for item in analyzed)} momentos sustentados por evidência",
        )

        stories_path = work_dir / "stories.json"
        stories_data = read_json(stories_path)
        if stories_data:
            final_candidates = self._candidates(stories_data)
        else:
            final_candidates = StoryBuilder(self.config, self.client).link(
                analyzed,
                cancelled=cancelled,
            )
            atomic_write_json(stories_path, [item.to_dict() for item in final_candidates])
        checkpoint(Stage.STORIES, 97, "Relações entre candidatos verificados")

        metadata["job_id"] = job.id
        metadata["analysis_profile"] = self.config.analysis_profile
        metadata["proposal_count"] = len(proposals)
        metadata["kept_count"] = sum(item.keep for item in final_candidates)
        result = write_report(
            result_dir,
            media,
            final_candidates,
            metadata=metadata,
            keep_internal=self.config.keep_internal_analysis,
        )
        checkpoint(Stage.REPORT, 100, "Timestamps salvos")

        if self.config.cleanup_temporary_files:
            shutil.rmtree(work_dir, ignore_errors=True)
        return result
