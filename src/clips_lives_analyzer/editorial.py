from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from clips_lives_analyzer.candidates import transcript_text
from clips_lives_analyzer.config import AnalyzerConfig
from clips_lives_analyzer.models import Candidate, TranscriptSegment
from clips_lives_analyzer.ollama import OllamaClient
from clips_lives_analyzer.storyboard import StoryboardBuilder
from clips_lives_analyzer.utils import clamp, format_timestamp


EDITORIAL_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {
            "type": "string",
            "enum": ["A", "B", "C", "discard"],
        },
        "start": {"type": "number"},
        "end": {"type": "number"},
        "category": {"type": "string"},
        "what_happened": {"type": "string"},
        "why_good": {"type": "string"},
        "evidence": {
            "type": "array",
            "items": {"type": "string"},
        },
        "confidence": {"type": "number"},
        "related_search_terms": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "decision",
        "start",
        "end",
        "category",
        "what_happened",
        "why_good",
        "evidence",
        "confidence",
        "related_search_terms",
    ],
}


class EditorialAnalyzer:
    def __init__(
        self,
        config: AnalyzerConfig,
        client: OllamaClient,
        editorial_rules: dict,
    ):
        self.config = config
        self.client = client
        self.rules = editorial_rules
        self.storyboards = StoryboardBuilder(config)

    def analyze(
        self,
        source: Path,
        candidate: Candidate,
        transcript: list[TranscriptSegment],
        work_dir: Path,
        *,
        cancelled: Callable[[], bool],
    ) -> Candidate:
        images = self.storyboards.build(
            source,
            candidate,
            work_dir,
            cancelled=cancelled,
        )
        text = transcript_text(transcript, candidate.start, candidate.end)
        system = (
            "Você é um analista editorial rigoroso de lives de League of Legends. "
            "Os storyboards estão em ordem e cada frame mostra seu timestamp global. "
            "Sua prioridade é não perder conteúdo bom, aceitando C fundamentado, mas "
            "descartando rotina vazia com firmeza. Movimento e volume não provam conteúdo. "
            "Analise fala e imagem juntas. Responda apenas no schema."
        )
        prompt = f"""JANELA: {format_timestamp(candidate.start)} a {format_timestamp(candidate.end)}
SINAIS QUE ABRIRAM A JANELA: {candidate.source_signals}
HIPÓTESE DO PRIMEIRO PASSE: {candidate.description}
EVIDÊNCIAS DO PRIMEIRO PASSE: {candidate.evidence}

TRANSCRIÇÃO:
{text or "(sem fala reconhecida)"}

CRITÉRIOS:
{json.dumps(self.rules, ensure_ascii=False)}

Decida com evidência concreta. Uma play mecânica bonita pode ser boa sem fala. Uma explicação
de item bizarro pode ser boa mesmo durante farm. Farm, caminhada, kill/morte comum e barulho
sem diferencial devem ser descartados. Ajuste início e fim para conter preparação, evento,
reação e payoff visíveis nesta janela. Use segundos globais dentro da janela."""
        decision = self.client.generate_json(
            model=self.config.vision_model,
            system=system,
            prompt=prompt,
            schema=EDITORIAL_SCHEMA,
            images=images,
        )
        grade = str(decision.get("decision", "discard"))
        confidence = clamp(float(decision.get("confidence", 0)), 0, 1)
        concrete_semantic = (
            "fala" in candidate.source_signals
            and bool(candidate.description.strip())
            and candidate.proposal_score >= 0.55
        )
        exceptional_signal = (
            "killfeed" in candidate.source_signals
            and "combate_visual" in candidate.source_signals
        )
        keep = grade in {"A", "B", "C"}
        if (
            not keep
            and self.config.analysis_profile == "coverage"
            and confidence < 0.76
            and (concrete_semantic or exceptional_signal)
        ):
            keep = True
            grade = "C"
            decision["why_good"] = (
                "Possível conteúdo preservado pelo modo cobertura após sinais conflitantes. "
                + str(decision.get("why_good", ""))
            ).strip()

        start = clamp(
            float(decision.get("start", candidate.start)),
            candidate.start,
            candidate.end,
        )
        end = clamp(
            float(decision.get("end", candidate.end)),
            start + 1,
            candidate.end,
        )
        if end - start < self.config.candidate_min_seconds and keep:
            midpoint = (start + end) / 2
            half = self.config.candidate_min_seconds / 2
            start = max(candidate.start, midpoint - half)
            end = min(candidate.end, midpoint + half)
        candidate.start = start
        candidate.end = end
        candidate.keep = keep
        candidate.grade = grade
        candidate.confidence = confidence
        candidate.category = str(decision.get("category", candidate.category))[:100]
        candidate.description = str(
            decision.get("what_happened", candidate.description)
        )[:1000]
        candidate.why_good = str(decision.get("why_good", ""))[:1200]
        candidate.evidence = [
            str(item)[:400] for item in decision.get("evidence", [])
        ][:10]
        return candidate
