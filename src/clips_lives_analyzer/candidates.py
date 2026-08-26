from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

from clips_lives_analyzer.config import AnalyzerConfig
from clips_lives_analyzer.models import Candidate, SignalPoint, TranscriptSegment
from clips_lives_analyzer.ollama import OllamaClient
from clips_lives_analyzer.utils import clamp, format_timestamp, merge_ranges


TRANSCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "category": {"type": "string"},
                    "description": {"type": "string"},
                    "evidence": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": [
                    "start",
                    "end",
                    "category",
                    "description",
                    "evidence",
                    "confidence",
                ],
            },
        }
    },
    "required": ["events"],
}


def candidate_id(start: float, end: float, source: str) -> str:
    raw = f"{round(start, 1)}:{round(end, 1)}:{source}".encode()
    return hashlib.sha1(raw).hexdigest()[:12]


def transcript_text(
    segments: list[TranscriptSegment],
    start: float,
    end: float,
) -> str:
    lines = []
    for segment in segments:
        if segment.end < start or segment.start > end:
            continue
        lines.append(f"[{format_timestamp(segment.start)}] {segment.text}")
    return "\n".join(lines)


def _transcript_chunks(
    segments: list[TranscriptSegment],
    duration: float,
    size: int,
    overlap: int,
) -> list[tuple[float, float, str]]:
    chunks = []
    start = 0.0
    while start < duration:
        end = min(duration, start + size)
        text = transcript_text(segments, start, end)
        if text.strip():
            chunks.append((start, end, text))
        if end >= duration:
            break
        start = end - overlap
    return chunks


def semantic_proposals(
    client: OllamaClient,
    config: AnalyzerConfig,
    segments: list[TranscriptSegment],
    duration: float,
    editorial_rules: dict,
    *,
    progress: Callable[[float, str], None],
    cancelled: Callable[[], bool],
) -> list[Candidate]:
    chunks = _transcript_chunks(
        segments,
        duration,
        config.transcript_chunk_seconds,
        config.transcript_overlap_seconds,
    )
    results = []
    system = (
        "Você é o primeiro passe de um analista editorial de lives de League of Legends. "
        "Seu trabalho é ter alta cobertura: encontrar falas que possam sustentar conteúdo, "
        "sem tratar rotina vazia como clip. Não avalie apenas kills. Os timestamps fornecidos "
        "são globais e devem ser copiados sem inventar valores. Responda apenas no schema."
    )
    rules = json.dumps(editorial_rules, ensure_ascii=False)
    for index, (chunk_start, chunk_end, text) in enumerate(chunks):
        if cancelled():
            raise InterruptedError
        prompt = f"""REGRAS EDITORIAIS:
{rules}

TRECHO ENTRE {format_timestamp(chunk_start)} E {format_timestamp(chunk_end)}:
{text}

Liste falas ou pequenas histórias concretas que merecem inspeção visual. Inclua explicação de
build/item/runa, Ciência/off-meta, hipótese, previsão, opinião, humor, reação, chat, X1, Arena,
Laboratório, Draft Lab e qualquer payoff citado. Não liste conversa banal. Uma explicação boa
durante farming continua relevante. Use segundos globais e não invente timestamps.
Amplie o começo e fim o suficiente para conter a ideia, mas permaneça dentro do trecho."""
        payload = client.generate_json(
            model=config.text_model,
            system=system,
            prompt=prompt,
            schema=TRANSCRIPT_SCHEMA,
        )
        for event in payload.get("events", []):
            try:
                start = clamp(float(event["start"]), chunk_start, chunk_end)
                end = clamp(float(event["end"]), start + 1, chunk_end)
                start = max(0, start - config.candidate_pre_seconds)
                end = min(duration, end + config.candidate_post_seconds)
                results.append(
                    Candidate(
                        id=candidate_id(start, end, "fala"),
                        start=start,
                        end=end,
                        source_signals=["fala"],
                        category=str(event["category"])[:80],
                        description=str(event["description"])[:500],
                        evidence=[str(event["evidence"])[:500]],
                        proposal_score=clamp(float(event["confidence"]), 0, 1),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        progress(
            (index + 1) / max(len(chunks), 1),
            f"Interpretando fala {index + 1} de {len(chunks)}",
        )
    return results


def signal_proposals(
    signals: list[SignalPoint],
    duration: float,
    config: AnalyzerConfig,
) -> list[Candidate]:
    if not signals:
        return []
    anchors: list[tuple[float, float, list[str]]] = []
    for point in signals:
        combat = (
            0.30 * point.motion
            + 0.26 * point.center_activity
            + 0.27 * point.killfeed_activity
            + 0.17 * point.audio_peak
        )
        sources = []
        if point.killfeed_activity >= 0.72:
            sources.append("killfeed")
        if point.motion >= 0.70 and point.center_activity >= 0.62:
            sources.append("combate_visual")
        if point.audio_peak >= 0.78 and point.audio_energy >= 0.58:
            sources.append("reação_audio")
        if point.scene_change >= 0.90 and point.hud_activity >= 0.65:
            sources.append("mudança_estado")
        if sources or combat >= 0.69:
            anchors.append((point.time, float(combat), sources or ["atividade_combinada"]))

    clustered = merge_ranges(
        [(time - 3, time + 3) for time, _score, _sources in anchors],
        gap=7,
    )
    results = []
    for start, end in clustered:
        nearby = [item for item in anchors if start - 1 <= item[0] <= end + 1]
        sources = sorted({source for _, _, item_sources in nearby for source in item_sources})
        score = max((item[1] for item in nearby), default=0.5)
        window_start = max(0, start - config.candidate_pre_seconds)
        window_end = min(duration, end + config.candidate_post_seconds)
        if window_end - window_start > config.candidate_max_seconds:
            midpoint = max(nearby, key=lambda item: item[1])[0]
            half = config.candidate_max_seconds / 2
            window_start = max(0, midpoint - half)
            window_end = min(duration, midpoint + half)
        results.append(
            Candidate(
                id=candidate_id(window_start, window_end, "sinais"),
                start=window_start,
                end=window_end,
                source_signals=sources,
                category="gameplay/reação a verificar",
                description="Atividade combinada de gameplay, HUD ou reação.",
                evidence=sources,
                proposal_score=clamp(score, 0, 1),
            )
        )
    return results


def _overlap_ratio(first: Candidate, second: Candidate) -> float:
    intersection = max(0.0, min(first.end, second.end) - max(first.start, second.start))
    shorter = max(1.0, min(first.end - first.start, second.end - second.start))
    return intersection / shorter


def merge_candidates(
    candidates: list[Candidate],
    duration: float,
    config: AnalyzerConfig,
) -> list[Candidate]:
    """Deduplica detecções sobrepostas do mesmo acontecimento, não eventos apenas próximos."""
    if not candidates:
        return []
    ordered = sorted(candidates, key=lambda item: (item.start, item.end))
    merged: list[Candidate] = []
    for candidate in ordered:
        if not merged:
            merged.append(candidate)
            continue
        previous = merged[-1]
        union_start = min(previous.start, candidate.start)
        union_end = max(previous.end, candidate.end)
        can_merge = (
            _overlap_ratio(previous, candidate) >= config.candidate_merge_overlap_ratio
            and union_end - union_start <= config.candidate_max_seconds
        )
        if not can_merge:
            merged.append(candidate)
            continue
        previous.start = union_start
        previous.end = min(duration, union_end)
        previous.source_signals = sorted(set(previous.source_signals + candidate.source_signals))
        previous.evidence = list(dict.fromkeys(previous.evidence + candidate.evidence))
        previous.proposal_score = max(previous.proposal_score, candidate.proposal_score)
        if candidate.description and candidate.description not in previous.description:
            previous.description = f"{previous.description} {candidate.description}".strip()[:900]
        previous.id = candidate_id(previous.start, previous.end, "+".join(previous.source_signals))
    return merged
