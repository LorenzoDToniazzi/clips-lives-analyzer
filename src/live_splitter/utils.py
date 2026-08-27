from __future__ import annotations

import os
import re
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".m4v", ".webm", ".ts"}


class ProcessCancelled(InterruptedError):
    pass


def format_timestamp(seconds: float) -> str:
    value = max(0, round(seconds))
    hours, remainder = divmod(value, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def safe_name(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip().rstrip(".")
    return cleaned or "live"


def unique_directory(root: Path, name: str) -> Path:
    candidate = root / safe_name(name)
    if not candidate.exists():
        return candidate
    counter = 2
    while True:
        candidate = root / f"{safe_name(name)} ({counter})"
        if not candidate.exists():
            return candidate
        counter += 1


def run_process(
    command: list[str],
    *,
    cancelled: Callable[[], bool] | None = None,
    timeout_seconds: float | None = None,
) -> subprocess.CompletedProcess[str]:
    creationflags = (
        subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    )
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )
    started = time.monotonic()
    while True:
        if cancelled and cancelled():
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
            raise ProcessCancelled
        if timeout_seconds and time.monotonic() - started > timeout_seconds:
            process.terminate()
            try:
                _stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                _stdout, stderr = process.communicate()
            raise RuntimeError(
                f"O comando excedeu {timeout_seconds:.0f}s.\n{stderr[-2000:]}"
            )
        try:
            stdout, stderr = process.communicate(timeout=0.25)
            break
        except subprocess.TimeoutExpired:
            continue
    if process.returncode:
        raise RuntimeError(
            f"O FFmpeg falhou com código {process.returncode}.\n{stderr[-3000:]}"
        )
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def atomic_replace(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, target)
