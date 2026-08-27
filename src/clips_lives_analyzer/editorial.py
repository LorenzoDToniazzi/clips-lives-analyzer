from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from clips_lives_analyzer.candidates import transcript_text
from clips_lives_analyzer.config import AnalyzerConfig
from clips_lives_analyzer.models import Candidate, TranscriptSegment
from clips_lives_analyzer.ollama import OllamaClient
from clips_lives_analyzer.storyboard import StoryboardBuilder
from clips_lives_analyzer.utils import clamp, format_timestamp


CATEGORY_VALUES = [
    "gameplay",
    "ciencia_build",
    "explicacao_educativo",
    "humor_reacao",
    "erro_situacao_negativa",
    "sistema_comunidade",
    "historia_payoff",
    "misto",
]

EDITORIAL_SCHEMA = {
    "type": "object",
    "properties": {
        "content_potential": {"type": "string", "enum": ["sim", "incerto", "nao"]},
        "decision": {"type": "string", "enum": ["A", "B", "C", "discard"]},
        "start": {"type": "number"},
        "end": {"type": "number"},
        "category": {"type": "string", "enum": CATEGORY_VALUES},
        "what_happened": {"type": "string"},
        "why_candidate": {"type": "string"},
        "routine_difference": {"type": "string"},
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "time": {"type": "number"},
                    "type": {"type": "string", "enum": ["speech", "visual", "context"]},
                    "observation": {"type": "string"},
                },
                "required": ["time", "type", "observation"],
            },
        },
        "context_note": {"type": "string"},
        "confidence": {"type": "number"},
        "related_search_terms": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "content_potential",
        "decision",
        "start",
        "end",
        "category",
        "what_happened",
        "why_candidate",
        "routine_difference",
        "evidence",
        "context_note",
        "confidence",
        "related_search_terms",
    ],
}


class EditorialAnalyzer:
    def __init__(self, config: AnalyzerConfig, client: OllamaClient, editorial_rules: dict):
        self.config = config
        self.client = client
        self.rules = editorial_rules
        self.storyboards = StoryboardBuilder(config)

    @staticmethod
    def _strong_prior(candidate: Candidate) -> bool:
        semantic = (
            "fala" in candidate.source_signals
            and bool(candidate.description.strip())
            and candidate.proposal_score >= 0.55
        )
        strong_visual = (
            "killfeed" in candidate.source_signals
            and "combate_visual" in candidate.source_signals
        ) or (
            "combate_visual" in candidate.source_signals
            and "reação_audio" in candidate.source_signals
        ) or (
            candidate.proposal_score >= 0.78
            and bool({"killfeed", "combate_visual", "reação_audio"} & set(candidate.source_signals))
        )
        return semantic or strong_visual

    @staticmethod
    def _normalize_evidence(value: Any) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        if not isinstance(value, list):
            return result
        for item in value:
            if isinstance(item, dict):
                try:
                    timestamp = float(item.get("time", 0))
                except (TypeError, ValueError):
                    timestamp = 0.0
                observation = str(item.get("observation", "")).strip()
                if not observation:
                    continue
                evidence_type = str(item.get("type", "context"))
                if evidence_type not in {"speech", "visual", "context"}:
                    evidence_type = "context"
                result.append({"time": timestamp, "type": evidence_type, "observation": observation[:500]})
            elif isinstance(item, str) and item.strip():
                result.append({"time": 0.0, "type": "context", "observation": item.strip()[:500]})
        return result[:10]

    def _prompt(
        self,
        candidate: Candidate,
        text: str,
        *,
        previous_decision: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        system = (
            "Você é um caçador editorial rigoroso de material bruto de lives de League of Legends. "
            "Sua prioridade é recall: não perder bons clips. Alguns falsos positivos fundamentados "
            "são aceitáveis; rotina vazia não é. Sinais técnicos apenas abriram a investigação e "
            "nunca provam conteúdo sozinhos. Uma boa play pode valer sem fala; uma boa explicação "
            "pode valer durante farm; contexto pode transformar kill, morte ou erro aparentemente "
            "comuns em conteúdo. Hook fraco não elimina material. Responda somente no schema."
        )
        previous = ""
        if previous_decision:
            previous = (
                "\nPRIMEIRA LEITURA COM MENOS FRAMES:\n"
                + json.dumps(previous_decision, ensure_ascii=False)
                + "\nReavalie com a evidência visual mais densa. Não preserve nem descarte só "
                "para concordar com a primeira leitura.\n"
            )
        prompt = f"""JANELA: {format_timestamp(candidate.start)} a {format_timestamp(candidate.end)}
SINAIS QUE PEDIRAM INSPEÇÃO: {candidate.source_signals}
HIPÓTESE DO PRIMEIRO PASSE: {candidate.description}
EVIDÊNCIAS DO PRIMEIRO PASSE: {candidate.evidence}

TRANSCRIÇÃO:
{text or "(sem fala reconhecida)"}

CRITÉRIOS:
{json.dumps(self.rules, ensure_ascii=False)}
{previous}
MÉTODO MÍNIMO:
1. Diga objetivamente o que aconteceu.
2. Decida se há potencial de conteúdo: sim, incerto ou não.
3. Escolha a razão principal entre as categorias permitidas.
4. Aponte evidência concreta com timestamp. Movimento, volume, HUD ou killfeed não bastam.
5. Explique o que diferencia o trecho de rotina. Para Ciência, identifique hipótese,
   explicação, teste ou resultado quando houver. Para morte/erro, explique por que o contexto
   torna a falha interessante. Para gameplay, diga o diferencial mecânico ou situacional.
6. Registre contexto anterior/posterior importante sem exigir que ele esteja nesta janela.
7. Classifique A/B/C/descarte. Se existe evidência concreta mas ainda há dúvida real, use C.

Ajuste início e fim somente dentro desta janela para preservar preparação, evento e reação/payoff
necessários. Use segundos globais. Não descarte porque já poderiam existir outros clips parecidos."""
        return system, prompt

    def _request(
        self,
        candidate: Candidate,
        text: str,
        images: list[Path],
        *,
        previous_decision: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        system, prompt = self._prompt(candidate, text, previous_decision=previous_decision)
        return self.client.generate_json(
            model=self.config.vision_model,
            system=system,
            prompt=prompt,
            schema=EDITORIAL_SCHEMA,
            images=images,
        )

    def _needs_dense_pass(self, decision: dict[str, Any], candidate: Candidate) -> bool:
        if self.config.storyboard_deep_frames <= self.config.storyboard_initial_frames:
            return False
        grade = str(decision.get("decision", "discard"))
        potential = str(decision.get("content_potential", "incerto"))
        confidence = clamp(float(decision.get("confidence", 0)), 0, 1)
        if grade in {"A", "B"} and confidence >= 0.78:
            return False
        if grade == "discard" and potential == "nao" and confidence >= 0.86 and not self._strong_prior(candidate):
            return False
        return True

    def analyze(
        self,
        source: Path,
        candidate: Candidate,
        transcript: list[TranscriptSegment],
        work_dir: Path,
        *,
        cancelled: Callable[[], bool],
    ) -> Candidate:
        text = transcript_text(transcript, candidate.start, candidate.end)
        initial_images = self.storyboards.build(
            source,
            candidate,
            work_dir,
            cancelled=cancelled,
            frame_count=self.config.storyboard_initial_frames,
        )
        initial_decision = self._request(candidate, text, initial_images)
        decision = initial_decision
        if self._needs_dense_pass(initial_decision, candidate):
            dense_images = self.storyboards.build(
                source,
                candidate,
                work_dir,
                cancelled=cancelled,
                frame_count=self.config.storyboard_deep_frames,
            )
            decision = self._request(candidate, text, dense_images, previous_decision=initial_decision)

        grade = str(decision.get("decision", "discard"))
        potential = str(decision.get("content_potential", "incerto"))
        confidence = clamp(float(decision.get("confidence", 0)), 0, 1)
        evidence_details = self._normalize_evidence(decision.get("evidence", []))
        has_evidence = bool(evidence_details)
        strong_prior = self._strong_prior(candidate)
        initial_evidence = self._normalize_evidence(initial_decision.get("evidence", []))

        keep = grade in {"A", "B", "C"}
        if not keep and self.config.analysis_profile == "coverage" and potential == "incerto" and (has_evidence or strong_prior):
            keep = True
            grade = "C"
        elif not keep and self.config.analysis_profile == "coverage" and strong_prior and confidence < 0.82:
            keep = True
            grade = "C"

        initial_grade = str(initial_decision.get("decision", "discard"))
        if (
            not keep
            and self.config.analysis_profile == "coverage"
            and initial_grade in {"A", "B", "C"}
            and initial_evidence
        ):
            keep = True
            grade = "C"
            if not evidence_details:
                evidence_details = initial_evidence

        if keep and not evidence_details:
            grade = "C"

        start = clamp(float(decision.get("start", candidate.start)), candidate.start, candidate.end)
        end = clamp(float(decision.get("end", candidate.end)), start + 1, candidate.end)
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
        candidate.content_potential = potential
        candidate.category = str(decision.get("category", candidate.category))[:100]
        candidate.description = str(decision.get("what_happened", candidate.description))[:1000]
        candidate.why_good = str(decision.get("why_candidate", ""))[:1200]
        candidate.routine_difference = str(decision.get("routine_difference", ""))[:900]
        candidate.context_note = str(decision.get("context_note", ""))[:900]
        candidate.evidence_details = evidence_details
        candidate.evidence = [
            f"{format_timestamp(item['time'])} [{item['type']}] {item['observation']}"
            for item in evidence_details
        ]
        candidate.related_search_terms = [
            str(item)[:120] for item in decision.get("related_search_terms", [])
        ][:12]
        return candidate
