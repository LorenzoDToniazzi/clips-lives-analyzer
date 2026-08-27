import json
import tempfile
import unittest
from pathlib import Path

from live_splitter.manifest import write_manifests
from live_splitter.models import MediaInfo, PartInfo


class ManifestTests(unittest.TestCase):
    def test_manifest_records_global_offsets_and_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "live 1.mp4"
            source.touch()
            media = MediaInfo(2400, 1000, 0, "h264", "aac", "mp4")
            parts = [
                PartInfo(
                    1,
                    "live 1 - arquivo 001.mp4",
                    0,
                    1200,
                    1200,
                    500,
                    0,
                    "h264",
                    "aac",
                ),
                PartInfo(
                    2,
                    "live 1 - arquivo 002.mp4",
                    1170,
                    2370,
                    1200,
                    500,
                    30,
                    "h264",
                    "aac",
                ),
            ]
            txt, json_path = write_manifests(root, source, media, parts)
            content = txt.read_text(encoding="utf-8")
            self.assertIn("Início global: 00:19:30", content)
            self.assertIn("Sobreposição anterior: 00:00:30", content)
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["parts"][1]["global_start"], 1170)


if __name__ == "__main__":
    unittest.main()
