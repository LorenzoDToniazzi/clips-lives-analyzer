from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from clips_lives_analyzer.models import Candidate, MediaInfo
from clips_lives_analyzer.utils import atomic_write_json, format_timestamp


def write_report(
    result_dir: Path,
    media: MediaInfo,
    candidates: list[Candidate],
    *,
    metadata: dict[str, Any],
    keep_internal: bool,
) -> Path:
    result_dir.mkdir(parents=True, exist_ok=True)
    kept = sorted(
        (candidate for candidate in candidates if candidate.keep),
        key=lambda item: item.start,
    )
    timestamp_path = result_dir / "timestamps.txt"
    lines = [Path(media.path).name, ""]
    lines.extend(
        f"{format_timestamp(item.start)} - {format_timestamp(item.end)}"
        for item in kept
    )
    timestamp_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    if keep_internal:
        atomic_write_json(
            result_dir / "analysis.json",
            {
                "source": media.to_dict(),
                "metadata": metadata,
                "candidates": [candidate.to_dict() for candidate in candidates],
            },
        )
        details = [
            f"# {Path(media.path).name}",
            "",
            f"Momentos encontrados: {len(kept)}",
            "",
        ]
        for index, item in enumerate(kept, 1):
            details.extend(
                [
                    f"## {index}. {format_timestamp(item.start)} - {format_timestamp(item.end)}",
                    "",
                    f"- Nota interna: {item.grade} ({item.confidence:.0%})",
                    f"- Categoria: {item.category}",
                    f"- O que aconteceu: {item.description}",
                    f"- Por que entrou: {item.why_good}",
                    "",
                ]
            )
        (result_dir / "details.md").write_text(
            "\n".join(details),
            encoding="utf-8",
        )
    return timestamp_path
