from __future__ import annotations

import io
from pathlib import Path

import pytest

from clips_lives_analyzer.config import AnalyzerConfig
from clips_lives_analyzer.transcriber import Transcriber


def test_auto_mode_refuses_silent_cpu_fallback(monkeypatch, tmp_path: Path):
    config = AnalyzerConfig(whisper_device="auto", whisper_allow_cpu_fallback=False)
    transcriber = Transcriber(config)
    monkeypatch.setattr(transcriber, "cuda_available", lambda: False)
    with pytest.raises(RuntimeError, match="fallback automático para CPU"):
        transcriber.transcribe(
            tmp_path / "audio.wav",
            10,
            progress=lambda _ratio, _message: None,
            cancelled=lambda: False,
        )


def test_auto_mode_can_use_cpu_when_explicitly_allowed(monkeypatch):
    config = AnalyzerConfig(whisper_device="auto", whisper_allow_cpu_fallback=True)
    transcriber = Transcriber(config)
    monkeypatch.setattr(transcriber, "cuda_available", lambda: False)
    device, reason = transcriber._select_device()
    assert device == "cpu"
    assert reason


def test_worker_startup_watchdog_stops_hung_process(monkeypatch, tmp_path: Path):
    class HungProcess:
        def __init__(self):
            self.stdout = io.StringIO("")
            self.stderr = io.StringIO("")
            self.returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = 1

        def kill(self):
            self.returncode = 1

        def wait(self, timeout=None):
            return self.returncode

    process = HungProcess()
    monkeypatch.setattr(
        "clips_lives_analyzer.transcriber.subprocess.Popen",
        lambda *args, **kwargs: process,
    )
    config = AnalyzerConfig()
    transcriber = Transcriber(config)

    with pytest.raises(RuntimeError, match="não conseguiu inicializar"):
        transcriber._run_worker(
            tmp_path / "audio.wav",
            10,
            device="cuda",
            progress=lambda _ratio, _message: None,
            cancelled=lambda: False,
            startup_timeout_seconds=0.05,
            inactivity_timeout_seconds=0.05,
        )
