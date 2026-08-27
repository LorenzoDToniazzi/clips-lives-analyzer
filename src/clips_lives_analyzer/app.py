from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from clips_lives_analyzer.config import load_config
from clips_lives_analyzer.database import QueueDatabase
from clips_lives_analyzer.doctor import run_diagnostics
from clips_lives_analyzer.models import JobStatus
from clips_lives_analyzer.paths import AppPaths
from clips_lives_analyzer.pipeline import AnalyzerPipeline
from clips_lives_analyzer.queue import QueueController


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clips-lives")
    subparsers = parser.add_subparsers(dest="command")
    analyze = subparsers.add_parser("analyze", help="adiciona VODs e processa a fila")
    analyze.add_argument("videos", nargs="+", type=Path)
    subparsers.add_parser("doctor", help="verifica a instalação")
    subparsers.add_parser("gui", help="abre a interface")
    return parser


def console_analyze(videos: list[Path], paths: AppPaths) -> int:
    config = load_config(paths)
    database = QueueDatabase(paths.database)
    pipeline = AnalyzerPipeline(paths, config)

    def event(name: str, job) -> None:
        if job and name in {"job_progress", "job_finished"}:
            print(
                f"\r{job.filename}: {job.progress:5.1f}% - {job.stage.value:18}",
                end="\n" if name == "job_finished" else "",
                flush=True,
            )

    queue = QueueController(database, pipeline, event)
    jobs = queue.add_files(videos)
    queue.start()
    try:
        while any(
            (current := database.get(job.id))
            and current.status in {JobStatus.QUEUED, JobStatus.RUNNING}
            for job in jobs
        ):
            time.sleep(1)
    except KeyboardInterrupt:
        for job in jobs:
            queue.cancel(job.id)
        return 130
    finally:
        queue.shutdown()
    failed = [database.get(job.id) for job in jobs]
    return 1 if any(job and job.status == JobStatus.FAILED for job in failed) else 0


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    paths = AppPaths.default()
    paths.ensure()
    if args.command == "doctor":
        config = load_config(paths)
        checks = run_diagnostics(paths, config)
        for check in checks:
            print(f"[{'OK' if check.ok else 'ATENÇÃO'}] {check.name}: {check.details}")
        required_failures = [
            check
            for check in checks
            if not check.ok
            and not (
                check.name == "Whisper GPU"
                and config.whisper_allow_cpu_fallback
            )
        ]
        raise SystemExit(1 if required_failures else 0)
    if args.command == "analyze":
        raise SystemExit(console_analyze(args.videos, paths))
    from clips_lives_analyzer.gui import launch

    launch(paths)


if __name__ == "__main__":
    main(sys.argv[1:])
