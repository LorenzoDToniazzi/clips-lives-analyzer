from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from clips_lives_analyzer.config import AnalyzerConfig
from clips_lives_analyzer.ollama import OllamaClient
from clips_lives_analyzer.paths import AppPaths
from clips_lives_analyzer.transcriber import Transcriber


@dataclass
class Check:
    name: str
    ok: bool
    details: str


def run_diagnostics(paths: AppPaths, config: AnalyzerConfig) -> list[Check]:
    checks = []
    for binary in ("ffmpeg", "ffprobe"):
        location = shutil.which(binary)
        checks.append(
            Check(binary, bool(location), location or "não encontrado no PATH")
        )
    try:
        client = OllamaClient(config)
        version = client.version()
        models = client.installed_models()
        required = {config.text_model, config.vision_model}
        missing = sorted(required - set(models))
        checks.append(Check("Ollama", True, f"versão {version}"))
        checks.append(
            Check(
                "Modelos",
                not missing,
                "prontos" if not missing else "faltando: " + ", ".join(missing),
            )
        )
    except Exception as exc:
        checks.append(Check("Ollama", False, str(exc)))
    cuda = Transcriber.cuda_available()
    checks.append(
        Check(
            "Whisper GPU",
            cuda,
            "CUDA disponível" if cuda else "usará CPU automaticamente",
        )
    )
    usage = shutil.disk_usage(paths.root.parent if paths.root.parent.exists() else Path.cwd())
    free_gb = usage.free / (1024**3)
    checks.append(
        Check(
            "Espaço livre",
            free_gb >= 20,
            f"{free_gb:.1f} GB livres; recomendado: 20 GB ou mais",
        )
    )
    return checks
