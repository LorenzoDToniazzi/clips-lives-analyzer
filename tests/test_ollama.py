import pytest

from clips_lives_analyzer.config import AnalyzerConfig
from clips_lives_analyzer.ollama import OllamaClient


def test_remote_ollama_url_is_rejected_for_privacy():
    config = AnalyzerConfig(ollama_url="https://example.com")
    with pytest.raises(ValueError):
        OllamaClient(config)


def test_local_ollama_urls_are_allowed():
    assert OllamaClient(AnalyzerConfig()).base_url == "http://127.0.0.1:11434"
