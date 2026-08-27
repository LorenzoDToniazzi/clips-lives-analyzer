from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from live_splitter.media import probe_media
from live_splitter.models import SplitConfig
from live_splitter.splitter import VodSplitter


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg necessário"
)
class SplitterIntegrationTests(unittest.TestCase):
    def _create_video(self, target: Path) -> None:
        subprocess.run(
            [
                shutil.which("ffmpeg") or "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=320x180:rate=30:duration=45",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=900:sample_rate=48000:duration=45",
                "-c:v",
                "libx264",
                "-g",
                "30",
                "-keyint_min",
                "30",
                "-sc_threshold",
                "0",
                "-c:a",
                "aac",
                str(target),
            ],
            check=True,
        )

    def test_split_preserves_codecs_order_size_and_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "live teste.mp4"
            self._create_video(source)
            source_before = source.stat()
            original = probe_media(source)
            config = SplitConfig(
                max_bytes=900_000,
                max_duration_seconds=20,
                overlap_seconds=3,
                size_target_ratio=0.9,
            )
            result = VodSplitter(config).split(source, root / "saida")
            self.assertGreaterEqual(len(result.parts), 3)
            self.assertEqual(
                [part.filename for part in result.parts],
                [
                    f"live teste - arquivo {index:03d}.mp4"
                    for index in range(1, len(result.parts) + 1)
                ],
            )
            for part in result.parts:
                path = result.output_dir / part.filename
                media = probe_media(path)
                self.assertLess(path.stat().st_size, config.max_bytes)
                self.assertLessEqual(media.duration, config.max_duration_seconds)
                self.assertEqual(media.video_codec, original.video_codec)
                self.assertEqual(media.audio_codec, original.audio_codec)
            self.assertGreater(result.parts[1].overlap_with_previous, 0)
            self.assertTrue(result.manifest_txt.exists())
            self.assertTrue(result.manifest_json.exists())
            source_after = source.stat()
            self.assertEqual(source_after.st_size, source_before.st_size)
            self.assertEqual(source_after.st_mtime_ns, source_before.st_mtime_ns)


if __name__ == "__main__":
    unittest.main()
