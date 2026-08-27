from __future__ import annotations

import json
import queue
import subprocess
import sys
import tempfile
import threading
import time
import wave
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

from clips_lives_analyzer.config import AnalyzerConfig
from clips_lives_analyzer.models import TranscriptSegment, TranscriptWord


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
    def _terminate(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    @staticmethod
    def _read_stream(
        stream: TextIO,
        source: str,
        output: queue.Queue[tuple[str, str]],
    ) -> None:
        try:
            for line in stream:
                output.put((source, line.rstrip("\r\n")))
        finally:
            stream.close()

    def _worker_command(self, audio_path: Path, device: str) -> list[str]:
        compute_type = (
            self.config.whisper_gpu_compute_type
            if device == "cuda"
            else self.config.whisper_cpu_compute_type
        )
        return [
            sys.executable,
            "-m",
            "clips_lives_analyzer.whisper_worker",
            "--audio",
            str(audio_path),
            "--model",
            self.config.whisper_model,
            "--device",
            device,
            "--compute-type",
            compute_type,
            "--language",
            self.config.language,
        ]

    def _run_worker(
        self,
        audio_path: Path,
        duration: float,
        *,
        device: str,
        progress: Callable[[float, str], None],
        cancelled: Callable[[], bool],
        startup_timeout_seconds: float | None = None,
        inactivity_timeout_seconds: float | None = None,
    ) -> tuple[list[TranscriptSegment], dict[str, Any]]:
        startup_timeout = float(
            startup_timeout_seconds
            if startup_timeout_seconds is not None
            else self.config.whisper_startup_timeout_seconds
        )
        inactivity_timeout = float(
            inactivity_timeout_seconds
            if inactivity_timeout_seconds is not None
            else self.config.whisper_inactivity_timeout_seconds
        )
        creationflags = (
            subprocess.CREATE_NO_WINDOW
            if hasattr(subprocess, "CREATE_NO_WINDOW")
            else 0
        )
        process = subprocess.Popen(
            self._worker_command(audio_path, device),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
        )
        assert process.stdout is not None
        assert process.stderr is not None

        messages: queue.Queue[tuple[str, str]] = queue.Queue()
        stdout_thread = threading.Thread(
            target=self._read_stream,
            args=(process.stdout, "stdout", messages),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=self._read_stream,
            args=(process.stderr, "stderr", messages),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        segments: list[TranscriptSegment] = []
        stderr_tail: deque[str] = deque(maxlen=30)
        metadata: dict[str, Any] | None = None
        worker_error: str | None = None
        phase = "startup"
        last_activity = time.monotonic()
        device_label = "GPU" if device == "cuda" else "CPU"
        progress(0, f"Carregando Whisper {self.config.whisper_model} na {device_label}")

        try:
            while True:
                if cancelled():
                    self._terminate(process)
                    raise InterruptedError

                now = time.monotonic()
                allowed = startup_timeout if phase == "startup" else inactivity_timeout
                if now - last_activity > allowed:
                    self._terminate(process)
                    if phase == "startup":
                        raise RuntimeError(
                            f"Whisper não conseguiu inicializar na {device_label} em "
                            f"{allowed:.0f}s. Isso costuma indicar problema de runtime CUDA/cuDNN "
                            "ou carregamento do CTranslate2."
                        )
                    raise RuntimeError(
                        f"Whisper ficou {allowed:.0f}s sem produzir progresso na {device_label}. "
                        "O processo foi encerrado para evitar uma análise infinita."
                    )

                try:
                    source, line = messages.get(timeout=0.25)
                except queue.Empty:
                    if process.poll() is not None and messages.empty():
                        break
                    continue

                if source == "stderr":
                    if line:
                        stderr_tail.append(line)
                    continue
                if not line:
                    continue

                last_activity = time.monotonic()
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    stderr_tail.append(f"stdout inválido: {line}")
                    continue

                event_name = event.get("event")
                if event_name == "model_loading":
                    progress(0, f"Inicializando Whisper na {device_label}")
                elif event_name == "model_loaded":
                    phase = "transcription"
                    progress(0.001, f"Whisper carregado na {device_label}; preparando transcrição")
                elif event_name == "transcription_started":
                    phase = "transcription"
                    progress(0.002, "Whisper iniciou a leitura do áudio")
                elif event_name == "segment":
                    words = [
                        TranscriptWord(
                            start=float(word["start"]),
                            end=float(word["end"]),
                            text=str(word["text"]),
                            probability=(
                                float(word["probability"])
                                if word.get("probability") is not None
                                else None
                            ),
                        )
                        for word in event.get("words", [])
                    ]
                    item = TranscriptSegment(
                        start=float(event["start"]),
                        end=float(event["end"]),
                        text=str(event.get("text", "")).strip(),
                        words=words,
                    )
                    segments.append(item)
                    progress(
                        min(1.0, item.end / max(duration, 1)),
                        f"Transcrevendo {item.end / 60:.1f} de {duration / 60:.1f} min",
                    )
                elif event_name == "done":
                    metadata = {
                        "language": str(event.get("language", self.config.language)),
                        "language_probability": float(event.get("language_probability", 0.0)),
                    }
                    break
                elif event_name == "error":
                    details = str(event.get("message") or "erro desconhecido")
                    trace = str(event.get("traceback") or "").strip()
                    worker_error = details + (f"\n{trace}" if trace else "")
                    break

            if metadata is None and worker_error is None and process.poll() is not None:
                worker_error = (
                    f"Processo do Whisper terminou inesperadamente com código {process.returncode}."
                )
        finally:
            if process.poll() is None:
                self._terminate(process)
            stdout_thread.join(timeout=1)
            stderr_thread.join(timeout=1)

        if worker_error:
            stderr_text = "\n".join(stderr_tail)
            if stderr_text:
                worker_error = f"{worker_error}\n{stderr_text}"
            raise RuntimeError(worker_error)
        if metadata is None:
            raise RuntimeError("Whisper terminou sem devolver metadados de transcrição.")
        return segments, metadata

    def gpu_runtime_check(self) -> tuple[bool, str]:
        if not self.cuda_available():
            return False, "CTranslate2 não detectou uma GPU CUDA disponível."
        with tempfile.TemporaryDirectory(prefix="clips-lives-whisper-") as temp_dir:
            audio_path = Path(temp_dir) / "smoke.wav"
            with wave.open(str(audio_path), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(16000)
                audio.writeframes(b"\x00\x00" * 16000)
            try:
                self._run_worker(
                    audio_path,
                    1.0,
                    device="cuda",
                    progress=lambda _ratio, _message: None,
                    cancelled=lambda: False,
                    startup_timeout_seconds=min(
                        float(self.config.whisper_startup_timeout_seconds), 90.0
                    ),
                    inactivity_timeout_seconds=60.0,
                )
            except Exception as exc:
                return False, str(exc).splitlines()[0]
        return True, "Inferência real do Whisper executada na GPU com sucesso."

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
            segments, info = self._run_worker(
                audio_path,
                duration,
                device=device,
                progress=progress,
                cancelled=cancelled,
            )
        except InterruptedError:
            raise
        except Exception as exc:
            can_fallback = (
                device == "cuda"
                and requested == "auto"
                and self.config.whisper_allow_cpu_fallback
            )
            if not can_fallback:
                if device == "cuda":
                    raise RuntimeError(
                        "O Whisper falhou ao executar na GPU. O processo foi encerrado em vez de "
                        "ficar preso indefinidamente. Verifique CUDA 12, cuBLAS e cuDNN compatíveis. "
                        f"Detalhe: {str(exc).splitlines()[0]}"
                    ) from exc
                raise
            fallback_reason = (
                f"Whisper falhou na GPU ({str(exc).splitlines()[0]}); "
                "fallback para CPU foi autorizado."
            )
            progress(0, fallback_reason)
            device = "cpu"
            segments, info = self._run_worker(
                audio_path,
                duration,
                device=device,
                progress=progress,
                cancelled=cancelled,
            )

        metadata = {
            "language": info["language"],
            "language_probability": float(info["language_probability"]),
            "duration": duration,
            "device": device,
            "model": self.config.whisper_model,
            "fallback_reason": fallback_reason,
        }
        return segments, metadata
