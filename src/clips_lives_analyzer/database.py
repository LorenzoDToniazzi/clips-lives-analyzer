from __future__ import annotations

import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Iterable

from clips_lives_analyzer.models import Job, JobStatus, Stage
from clips_lives_analyzer.utils import fingerprint_file, is_supported_video, utc_now


class QueueDatabase:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    progress REAL NOT NULL DEFAULT 0,
                    priority INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error TEXT,
                    result_path TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_next
                    ON jobs(status, priority, created_at);
                CREATE INDEX IF NOT EXISTS idx_jobs_fingerprint
                    ON jobs(fingerprint);
                CREATE TABLE IF NOT EXISTS job_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> Job:
        return Job(
            id=row["id"],
            source_path=row["source_path"],
            fingerprint=row["fingerprint"],
            status=JobStatus(row["status"]),
            stage=Stage(row["stage"]),
            progress=float(row["progress"]),
            priority=int(row["priority"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            error=row["error"],
            result_path=row["result_path"],
            cancel_requested=bool(row["cancel_requested"]),
        )

    def add(self, source: Path, priority: int | None = None) -> tuple[Job, bool]:
        source = source.resolve(strict=True)
        if not is_supported_video(source):
            raise ValueError(f"Formato de vídeo não suportado: {source.name}")
        fingerprint = fingerprint_file(source)
        with self._lock, self._connect() as connection:
            duplicate = connection.execute(
                """
                SELECT * FROM jobs
                WHERE fingerprint = ? AND status != ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (fingerprint, JobStatus.CANCELLED.value),
            ).fetchone()
            if duplicate:
                return self._row_to_job(duplicate), False
            if priority is None:
                row = connection.execute("SELECT COALESCE(MAX(priority), 0) + 10 FROM jobs").fetchone()
                priority = int(row[0])
            now = utc_now()
            job_id = uuid.uuid4().hex[:16]
            connection.execute(
                """
                INSERT INTO jobs (
                    id, source_path, fingerprint, status, stage, progress,
                    priority, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    job_id,
                    str(source),
                    fingerprint,
                    JobStatus.QUEUED.value,
                    Stage.QUEUED.value,
                    priority,
                    now,
                    now,
                ),
            )
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return self._row_to_job(row), True

    def add_many(self, sources: Iterable[Path]) -> list[tuple[Job, bool]]:
        return [self.add(source) for source in sources]

    def get(self, job_id: str) -> Job | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def list(self) -> list[Job]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM jobs
                ORDER BY
                    CASE status
                        WHEN 'running' THEN 0
                        WHEN 'queued' THEN 1
                        WHEN 'paused' THEN 2
                        ELSE 3
                    END,
                    priority, created_at
                """
            ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def claim_next(self) -> Job | None:
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM jobs
                WHERE status = ?
                ORDER BY priority, created_at
                LIMIT 1
                """,
                (JobStatus.QUEUED.value,),
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            now = utc_now()
            connection.execute(
                """
                UPDATE jobs SET status = ?, updated_at = ?, cancel_requested = 0
                WHERE id = ?
                """,
                (JobStatus.RUNNING.value, now, row["id"]),
            )
            connection.commit()
            return self.get(row["id"])

    def update(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        stage: Stage | None = None,
        progress: float | None = None,
        error: str | None = None,
        result_path: str | None = None,
        clear_error: bool = False,
    ) -> None:
        assignments = ["updated_at = ?"]
        values: list[object] = [utc_now()]
        if status is not None:
            assignments.append("status = ?")
            values.append(status.value)
        if stage is not None:
            assignments.append("stage = ?")
            values.append(stage.value)
        if progress is not None:
            assignments.append("progress = ?")
            values.append(max(0.0, min(100.0, progress)))
        if error is not None or clear_error:
            assignments.append("error = ?")
            values.append(error)
        if result_path is not None:
            assignments.append("result_path = ?")
            values.append(result_path)
        values.append(job_id)
        with self._lock, self._connect() as connection:
            connection.execute(
                f"UPDATE jobs SET {', '.join(assignments)} WHERE id = ?",
                values,
            )

    def log(self, job_id: str, message: str, level: str = "info") -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO job_events(job_id, created_at, level, message) VALUES (?, ?, ?, ?)",
                (job_id, utc_now(), level, message),
            )

    def events(self, job_id: str, limit: int = 200) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT created_at, level, message FROM job_events
                WHERE job_id = ? ORDER BY id DESC LIMIT ?
                """,
                (job_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def recover_interrupted(self) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = ?, updated_at = ?, cancel_requested = 0
                WHERE status = ?
                """,
                (JobStatus.QUEUED.value, utc_now(), JobStatus.RUNNING.value),
            )
            return cursor.rowcount

    def request_cancel(self, job_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE jobs SET cancel_requested = 1, updated_at = ? WHERE id = ?",
                (utc_now(), job_id),
            )

    def is_cancel_requested(self, job_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT cancel_requested FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return bool(row and row[0])

    def retry(self, job_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs SET status = ?, stage = ?, progress = 0, error = NULL,
                    cancel_requested = 0, updated_at = ?
                WHERE id = ?
                """,
                (
                    JobStatus.QUEUED.value,
                    Stage.QUEUED.value,
                    utc_now(),
                    job_id,
                ),
            )

    def remove(self, job_id: str) -> None:
        with self._connect() as connection:
            row = connection.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row and row[0] == JobStatus.RUNNING.value:
                raise RuntimeError("Cancele o arquivo em execução antes de removê-lo")
            connection.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
