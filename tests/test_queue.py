import time
from pathlib import Path

from clips_lives_analyzer.database import QueueDatabase
from clips_lives_analyzer.models import JobStatus, Stage
from clips_lives_analyzer.queue import QueueController


class FakeProcessor:
    def __init__(self, result: Path):
        self.result = result

    def process(self, _job, progress, cancelled):
        progress(Stage.TRANSCRIBE, 40, "transcrição")
        if cancelled():
            raise InterruptedError
        self.result.write_text("live.mp4\n\n00:00:01 - 00:00:20\n", encoding="utf-8")
        return self.result


def test_queue_processes_multiple_files_sequentially(tmp_path: Path):
    database = QueueDatabase(tmp_path / "queue.sqlite3")
    result = tmp_path / "timestamps.txt"
    controller = QueueController(database, FakeProcessor(result))
    videos = []
    for index in range(2):
        video = tmp_path / f"live-{index}.mp4"
        video.write_bytes(f"vod-{index}".encode())
        videos.append(video)
    jobs = controller.add_files(videos)
    controller.start()
    deadline = time.time() + 5
    while time.time() < deadline:
        if all(database.get(job.id).status == JobStatus.COMPLETED for job in jobs):
            break
        time.sleep(0.05)
    controller.shutdown()
    assert all(database.get(job.id).status == JobStatus.COMPLETED for job in jobs)
