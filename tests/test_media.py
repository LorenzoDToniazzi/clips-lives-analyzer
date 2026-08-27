import sys

from clips_lives_analyzer.media import run_checked


def test_run_checked_consumes_large_stdout_without_deadlock():
    payload_size = 1024 * 1024
    result = run_checked(
        [sys.executable, "-c", f"import sys; sys.stdout.write('x' * {payload_size})"],
        timeout_seconds=10,
    )
    assert len(result.stdout) == payload_size
