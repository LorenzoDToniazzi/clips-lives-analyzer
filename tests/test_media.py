import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from live_splitter.media import require_tools


class ToolDiscoveryTests(unittest.TestCase):
    def test_finds_tools_in_configured_portable_directory(self) -> None:
        executable_suffix = ".exe" if os.name == "nt" else ""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ffmpeg = root / f"ffmpeg{executable_suffix}"
            ffprobe = root / f"ffprobe{executable_suffix}"
            ffmpeg.touch()
            ffprobe.touch()
            with patch.dict(
                os.environ,
                {"LIVE_SPLITTER_FFMPEG_DIR": str(root)},
                clear=False,
            ):
                self.assertEqual(require_tools(), (str(ffmpeg), str(ffprobe)))


if __name__ == "__main__":
    unittest.main()
