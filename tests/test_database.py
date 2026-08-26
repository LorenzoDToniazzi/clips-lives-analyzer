from pathlib import Path

from clips_lives_analyzer.database import QueueDatabase
from clips_lives_analyzer.models import JobStatus, Stage


def test_queue_is_persistent_and_deduplicates(tmp_path: Path):
    database = QueueDatabase(tmp_path / "queue.sqlite3")
    video = tmp_path / "live.mp4"
    video.write_bytes(b"fake-vod")

    first, created = database.add(video)
    duplicate, duplicate_created = database.add(video)

    assert created is True
    assert duplicate_created is False
    assert duplicate.id == first.id
    assert database.claim_next().id == first.id
    assert database.get(first.id).status == JobStatus.RUNNING

    reopened = QueueDatabase(tmp_path / "queue.sqlite3")
    assert reopened.recover_interrupted() == 1
    assert reopened.get(first.id).status == JobStatus.QUEUED


def test_retry_clears_failure(tmp_path: Path):
    database = QueueDatabase(tmp_path / "queue.sqlite3")
    video = tmp_path / "live.mkv"
    video.write_bytes(b"fake")
    job, _ = database.add(video)
    database.update(
        job.id,
        status=JobStatus.FAILED,
        stage=Stage.TRANSCRIBE,
        progress=31,
        error="boom",
    )

    database.retry(job.id)
    retried = database.get(job.id)
    assert retried.status == JobStatus.QUEUED
    assert retried.stage == Stage.QUEUED
    assert retried.progress == 0
    assert retried.error is None
