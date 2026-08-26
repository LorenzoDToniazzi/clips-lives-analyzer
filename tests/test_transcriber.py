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
