from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from live_splitter.manifest import write_manifests
from live_splitter.models import MediaInfo, PartInfo, SplitResult
from live_splitter.transcription import (
    Transcript,
    TranscriptSegment,
    TranscriptWord,
    transcribe_split_result,
    update_manifest_transcription,
    write_transcription_files,
)


class TranscriptionFileTests(unittest.TestCase):
    def _result(self, root: Path) -> SplitResult:
        source = root / "live 3.final.mp4"
        source.touch()
        output = root / "saida"
        output.mkdir()
        parts = [
            PartInfo(
                1,
                "live 3.final - arquivo 001.mp4",
                0,
                20,
                20,
                100,
                0,
                "h264",
                "aac",
            ),
            PartInfo(
                2,
                "live 3.final - arquivo 002.mp4",
                17,
                37,
                20,
                100,
                3,
                "h264",
                "aac",
            ),
        ]
        media = MediaInfo(37.25, 200, 0, "h264", "aac", "mp4")
        manifest_txt, manifest_json = write_manifests(output, source, media, parts)
        return SplitResult(
            source=source,
            output_dir=output,
            parts=parts,
            manifest_txt=manifest_txt,
            manifest_json=manifest_json,
        )

    def _transcript(self) -> Transcript:
        return Transcript(
            source_file="live 3.final.mp4",
            duration_seconds=37,
            language="pt",
            language_probability=1.0,
            model="large-v3",
            device="cpu",
            compute_type="int8",
            generated_at="2026-08-28T00:00:00+00:00",
            segments=(
                TranscriptSegment(
                    "live 3.final-segmento-000001",
                    18,
                    19,
                    "Momento repetido na sobreposição.",
                    (
                        TranscriptWord(18, 18.5, " Momento", 0.99),
                        TranscriptWord(18.5, 19, " repetido", 0.98),
                    ),
                ),
                TranscriptSegment(
                    "live 3.final-segmento-000002",
                    21,
                    22,
                    "Somente no segundo arquivo.",
                    (TranscriptWord(21, 22, " Somente no segundo arquivo.", 0.97),),
                ),
            ),
        )

    def test_writes_master_and_part_files_with_manifest_offsets(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = self._result(Path(temp))
            artifacts = write_transcription_files(result, self._transcript())
            update_manifest_transcription(result, artifacts=artifacts)

            self.assertTrue(artifacts.master_txt.exists())
            self.assertTrue(artifacts.master_srt.exists())
            self.assertEqual(
                artifacts.master_json.name,
                "TRANSCRICAO - live 3.final.json",
            )
            first = json.loads(
                (
                    result.output_dir
                    / "live 3.final - arquivo 001 - transcricao.json"
                ).read_text(encoding="utf-8")
            )
            second = json.loads(
                (
                    result.output_dir
                    / "live 3.final - arquivo 002 - transcricao.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(first["segments"][0]["local_start"], 18)
            self.assertEqual(second["segments"][0]["local_start"], 1)
            self.assertEqual(
                first["segments"][0]["segment_id"],
                second["segments"][0]["segment_id"],
            )
            self.assertEqual(second["segments"][1]["local_start"], 4)
            manifest = json.loads(result.manifest_json.read_text(encoding="utf-8"))
            self.assertEqual(manifest["transcription"]["status"], "concluida")
            self.assertEqual(manifest["transcription"]["language"], "pt")

    def test_failed_transcription_does_not_change_part_offsets(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = self._result(Path(temp))
            before = json.loads(result.manifest_json.read_text(encoding="utf-8"))
            update_manifest_transcription(result, error="modelo indisponível")
            after = json.loads(result.manifest_json.read_text(encoding="utf-8"))
            self.assertEqual(before["parts"], after["parts"])
            self.assertEqual(after["transcription"]["status"], "falhou")
            self.assertIn(
                "As partes de vídeo e os offsets do manifesto continuam válidos",
                result.manifest_txt.read_text(encoding="utf-8"),
            )

    def test_pipeline_uses_total_duration_from_manifest(self) -> None:
        class FakeTranscriber:
            received_duration: float | None = None

            def transcribe(self, _source, *, duration, progress, cancelled):
                self.received_duration = duration
                return TranscriptionFileTests()._transcript()

        with tempfile.TemporaryDirectory() as temp:
            result = self._result(Path(temp))
            transcriber = FakeTranscriber()
            transcribe_split_result(result, transcriber=transcriber)
            self.assertEqual(transcriber.received_duration, 37.25)


if __name__ == "__main__":
    unittest.main()
