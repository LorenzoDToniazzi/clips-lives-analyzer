from __future__ import annotations

import json
from pathlib import Path

from live_splitter.models import MediaInfo, PartInfo
from live_splitter.utils import format_timestamp


def write_manifests(
    output_dir: Path,
    source: Path,
    media: MediaInfo,
    parts: list[PartInfo],
) -> tuple[Path, Path]:
    title = source.stem
    txt_path = output_dir / f"MANIFESTO - {title}.txt"
    json_path = output_dir / f"MANIFESTO - {title}.json"
    lines = [
        f"LIVE: {title}",
        f"ARQUIVO ORIGINAL: {source.name}",
        f"DURAÇÃO TOTAL: {format_timestamp(media.duration)}",
        "",
        "COMO CONVERTER:",
        "timestamp da live = início global do arquivo + timestamp encontrado no arquivo",
        "Use sempre o início global informado abaixo. A sobreposição real aparece em cada item.",
        "Se o mesmo momento aparecer em dois arquivos, mantenha somente uma ocorrência.",
        "",
    ]
    for part in parts:
        lines.extend(
            [
                f"ARQUIVO {part.index:03d}: {part.filename}",
                f"  Início global: {format_timestamp(part.global_start)}",
                f"  Fim global: {format_timestamp(part.global_end)}",
                f"  Duração local: {format_timestamp(part.local_duration)}",
                f"  Sobreposição anterior: {format_timestamp(part.overlap_with_previous)}",
                f"  Tamanho: {part.size_bytes / 1_000_000:.2f} MB",
                "",
            ]
        )
    txt_path.write_text("\n".join(lines), encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "live": title,
                "source_file": source.name,
                "duration_seconds": media.duration,
                "parts": [item.to_dict() for item in parts],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return txt_path, json_path
