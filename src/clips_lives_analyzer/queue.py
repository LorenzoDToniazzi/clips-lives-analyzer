from __future__ import annotations

import threading
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from clips_lives_analyzer.database import QueueDatabase
from clips_lives_analyzer.models import Job, JobStatus, Stage


class Processor(Protocol):
    def process(
        self,
        job: Job,
        progress: Callable[[Stage, float, str], None],
        cancelled: Callable[[], bool],
    ) -> Path: ...


QueueEvent = Callable[[str, Job | None], None]


class QueueController:
    def __init__(
        self,
        database: QueueDatabase,
        processor: Processor,
        on_event: QueueEvent | None = None,
    ):
        self.database = database
        self.processor = processor
        self.on_event = on_event or (lambda _event, _job: None)
        self._pause = threading.Event()
        self._shutdown = threading.Event()
        self._wakeup = threading.Event()
        self._thread: threading.Thread | None = None
        self.database.recover_interrupted()

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @property
    def paused(self) -> bool:
        return self._pause.is_set()

    def add_files(self, sources: list[Path]) -> list[Job]:
        jobs = []
        for source in sources:
            job, created = self.database.add(source)
            jobs.append(job)
            self.database.log(
                job.id,
                "Adicionado à fila." if created else "Arquivo já estava na fila.",
            )
        self._wakeup.set()
        self.on_event("queue_changed", None)
        return jobs

    def start(self) -> None:
        self._pause.clear()
        self._shutdown.clear()
        if not self.running:
            self._thread = threading.Thread(target=self._run, name="vod-queue", daemon=True)
            self._thread.start()
        self._wakeup.set()
        self.on_event("queue_started", None)

    def pause_after_current(self) -> None:
        self._pause.set()
        self.on_event("queue_paused", None)

    def resume(self) -> None:
        self.start()

    def shutdown(self, wait: bool = True) -> None:
        self._shutdown.set()
        self._wakeup.set()
        if wait and self._thread:
            self._thread.join(timeout=10)

    def cancel(self, job_id: str) -> None:
        job = self.database.get(job_id)
        if not job:
            return
        if job.status == JobStatus.RUNNING:
            self.database.request_cancel(job_id)
        elif job.status in {JobStatus.QUEUED, JobStatus.PAUSED}:
            self.database.update(job_id, status=JobStatus.CANCELLED)
        self.on_event("queue_changed", self.database.get(job_id))

    def _progress(self, job_id: str, stage: Stage, value: float, message: str) -> None:
        self.database.update(job_id, stage=stage, progress=value)
        if message:
            self.database.log(job_id, message)
        self.on_event("job_progress", self.database.get(job_id))

    def _run(self) -> None:
        while not self._shutdown.is_set():
            if self._pause.is_set():
                self._wakeup.wait(timeout=1)
                self._wakeup.clear()
                continue
            job = self.database.claim_next()
            if job is None:
                self._wakeup.wait(timeout=2)
                self._wakeup.clear()
                continue
            self.on_event("job_started", job)
            try:
                result = self.processor.process(
                    job,
                    lambda stage, value, message: self._progress(
                        job.id, stage, value, message
                    ),
                    lambda: self._shutdown.is_set()
                    or self.database.is_cancel_requested(job.id),
                )
                if self.database.is_cancel_requested(job.id):
                    self.database.update(job.id, status=JobStatus.CANCELLED)
                    self.database.log(job.id, "Análise cancelada.", "warning")
                else:
                    self.database.update(
                        job.id,
                        status=JobStatus.COMPLETED,
                        stage=Stage.COMPLETE,
                        progress=100,
                        result_path=str(result),
                    )
                    self.database.log(job.id, "Análise concluída.")
            except InterruptedError:
                if self._shutdown.is_set() and not self.database.is_cancel_requested(job.id):
                    self.database.update(job.id, status=JobStatus.QUEUED)
                    self.database.log(
                        job.id,
                        "Interrompido com segurança; será retomado ao abrir.",
                        "warning",
                    )
                else:
                    self.database.update(job.id, status=JobStatus.CANCELLED)
                    self.database.log(job.id, "Análise cancelada.", "warning")
            except Exception as exc:
                self.database.update(
                    job.id,
                    status=JobStatus.FAILED,
                    error=f"{type(exc).__name__}: {exc}",
                )
                self.database.log(job.id, traceback.format_exc(), "error")
            self.on_event("job_finished", self.database.get(job.id))
