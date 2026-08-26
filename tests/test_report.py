from pathlib import Path

from clips_lives_analyzer.models import Candidate, MediaInfo
from clips_lives_analyzer.report import write_report


def test_primary_report_contains_only_filename_and_timestamps(tmp_path: Path):
    media = MediaInfo(
        path=str(tmp_path / "live.mp4"),
        duration=100,
        width=1920,
        height=1080,
        fps=60,
        video_codec="h264",
        audio_codec="aac",
        size_bytes=10,
    )
    candidates = [
        Candidate("a", 10, 20, ["fala"], keep=True, grade="B"),
        Candidate("b", 30, 40, ["motion"], keep=False, grade="discard"),
    ]
    result = write_report(
        tmp_path / "result",
        media,
        candidates,
        metadata={},
        keep_internal=True,
    )
    text = result.read_text(encoding="utf-8")
    assert text == "live.mp4\n\n00:00:10 - 00:00:20\n"
    assert "00:00:30" not in text
    assert (result.parent / "analysis.json").exists()
