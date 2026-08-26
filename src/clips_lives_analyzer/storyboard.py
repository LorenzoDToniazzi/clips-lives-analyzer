from __future__ import annotations

import math
import shutil
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from clips_lives_analyzer.config import AnalyzerConfig
from clips_lives_analyzer.media import require_binary, run_checked
from clips_lives_analyzer.models import Candidate
from clips_lives_analyzer.utils import format_timestamp


class StoryboardBuilder:
    def __init__(self, config: AnalyzerConfig):
        self.config = config

    def build(
        self,
        source: Path,
        candidate: Candidate,
        work_dir: Path,
        *,
        cancelled: Callable[[], bool],
    ) -> list[Path]:
        candidate_dir = work_dir / "storyboards" / candidate.id
        sheets = sorted(candidate_dir.glob("sheet_*.jpg"))
        if sheets:
            return sheets
        raw_dir = candidate_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        duration = max(1.0, candidate.end - candidate.start)
        frame_count = self.config.storyboard_frames
        sample_fps = frame_count / duration
        ffmpeg = require_binary("ffmpeg")
        run_checked(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                f"{candidate.start:.3f}",
                "-i",
                str(source),
                "-t",
                f"{duration:.3f}",
                "-vf",
                f"fps={sample_fps:.8f},scale=640:-2",
                "-frames:v",
                str(frame_count),
                "-q:v",
                "3",
                str(raw_dir / "frame_%03d.jpg"),
            ],
            cancelled=cancelled,
        )
        raw_frames = sorted(raw_dir.glob("frame_*.jpg"))
        if not raw_frames:
            raise RuntimeError(f"Não foi possível gerar storyboard em {candidate.start:.1f}s")
        columns = self.config.storyboard_columns
        rows = 3
        per_sheet = columns * rows
        output: list[Path] = []
        for sheet_index in range(math.ceil(len(raw_frames) / per_sheet)):
            group = raw_frames[sheet_index * per_sheet : (sheet_index + 1) * per_sheet]
            sheet_path = candidate_dir / f"sheet_{sheet_index + 1:02d}.jpg"
            self._compose_sheet(
                group,
                sheet_path,
                candidate.start,
                duration,
                len(raw_frames),
                sheet_index * per_sheet,
                columns,
                rows,
            )
            output.append(sheet_path)
        shutil.rmtree(raw_dir, ignore_errors=True)
        return output

    @staticmethod
    def _compose_sheet(
        frames: list[Path],
        target: Path,
        start: float,
        duration: float,
        total_frames: int,
        offset: int,
        columns: int,
        rows: int,
    ) -> None:
        cell_width, image_height, label_height = 640, 360, 34
        sheet = Image.new(
            "RGB",
            (columns * cell_width, rows * (image_height + label_height)),
            "black",
        )
        draw = ImageDraw.Draw(sheet)
        font = ImageFont.load_default()
        for local_index, frame_path in enumerate(frames):
            global_index = offset + local_index
            with Image.open(frame_path) as image:
                image = image.convert("RGB")
                image.thumbnail((cell_width, image_height))
                canvas = Image.new("RGB", (cell_width, image_height), "black")
                canvas.paste(
                    image,
                    ((cell_width - image.width) // 2, (image_height - image.height) // 2),
                )
            column = local_index % columns
            row = local_index // columns
            x = column * cell_width
            y = row * (image_height + label_height)
            sheet.paste(canvas, (x, y))
            time = start + duration * ((global_index + 0.5) / max(total_frames, 1))
            draw.rectangle(
                (x, y + image_height, x + cell_width, y + image_height + label_height),
                fill=(12, 12, 12),
            )
            draw.text(
                (x + 10, y + image_height + 5),
                f"Frame {global_index + 1} - {format_timestamp(time)}",
                fill="white",
                font=font,
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(target, "JPEG", quality=84, optimize=True)
