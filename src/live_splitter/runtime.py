from __future__ import annotations

import logging
import os
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_FOLDER = "Picotador de Lives"


def data_directory() -> Path:
    configured = os.environ.get("LIVE_SPLITTER_DATA_DIR")
    candidates = [Path(configured)] if configured else []
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / APP_FOLDER)
    candidates.append(Path(tempfile.gettempdir()) / APP_FOLDER)
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except OSError:
            continue
    raise RuntimeError("Não foi possível criar a pasta de diagnóstico do programa")


def configure_logging() -> Path:
    log_path = data_directory() / "picotador.log"
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(handler, RotatingFileHandler) for handler in root.handlers):
        handler = RotatingFileHandler(
            log_path,
            maxBytes=2_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )
        root.addHandler(handler)
    return log_path
