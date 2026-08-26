from pathlib import Path

from clips_lives_analyzer.utils import fingerprint_file, format_timestamp, merge_ranges


def test_format_timestamp_rounds_and_supports_long_vods():
    assert format_timestamp(0) == "00:00:00"
    assert format_timestamp(3661.4) == "01:01:01"
    assert format_timestamp(7201) == "02:00:01"


def test_merge_ranges_uses_requested_gap():
    assert merge_ranges([(0, 5), (8, 10), (30, 40)], gap=3) == [(0, 10), (30, 40)]


def test_fingerprint_changes_with_file_content(tmp_path: Path):
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    first.write_bytes(b"a" * 2048)
    second.write_bytes(b"a" * 2047 + b"b")
    assert fingerprint_file(first) != fingerprint_file(second)
