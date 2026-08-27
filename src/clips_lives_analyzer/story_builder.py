from __future__ import annotations

import json
from collections.abc import Callable

from clips_lives_analyzer.config import AnalyzerConfig
from clips_lives_analyzer.models import Candidate
from clips_lives_analyzer.ollama import OllamaClient
from clips_lives_analyzer.utils import format_timestamp


STORY_SCHEMA = {
    "type": "object",
    "properties": {
        "links": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ids": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                    "upgrade_to": {"type": "string", "enum": ["A", "B", "C"]},
                },
                "required": ["ids", "reason", "upgrade_to"],
            },
        }
    },
    "required": ["links"],
}

GRADE_ORDER = {"discard": 0, "C": 1, "B": 2, "A": 3}


class StoryBuilder:
    """Relaciona candidatos já encontrados; não faz busca ativa por eventos ausentes."""

    def __init__(self, config: AnalyzerConfig, client: OllamaClient):
        self.config = config
        self.client = client

    def link(
        self,
        candidates: list[Candidate],
        *,
        cancelled: Callable[[], bool],
    ) -> list[Candidate]:
        kept = [candidate for candidate in candidates if candidate.keep]
        if len(kept) < 2:
            return candidates
        if cancelled():
            raise InterruptedError
        compact = [
            {
                "id": item.id,
                "timestamp": f"{format_timestamp(item.start)}-{format_timestamp(item.end)}",
                "category": item.category,
                "event": item.description,
                "why": item.why_good,
                "context": item.context_note,
                "search_terms": item.related_search_terms[:6],
                "evidence": item.evidence[:3],
            }
            for item in kept
        ]
        prompt = f"""CANDIDATOS EM ORDEM TEMPORAL:
{json.dumps(compact, ensure_ascii=False)}

Relacione somente histórias reais entre momentos diferentes: hipótese->teste, explicação de
item->uso/payoff, promessa->sucesso ou desastre, primeira tentativa->repetição, apresentação
de sistema->bug/resultado, reclamação->problema repetido ou callback claro. Não relacione
momentos apenas porque são da mesma partida. IDs podem estar distantes até
{self.config.story_max_gap_seconds} segundos. Não crie timestamps e não funda nem remova
candidatos: momentos relacionados continuam válidos individualmente."""
        response = self.client.generate_json(
            model=self.config.text_model,
            system=(
                "Você relaciona histórias editoriais já detectadas em uma live de League of "
                "Legends. Se não houver conexão clara, retorne links vazio. Esta etapa não "
                "procura eventos que não estejam na lista. Responda só no schema."
            ),
            prompt=prompt,
            schema=STORY_SCHEMA,
            num_ctx=self.config.ollama_story_context,
        )
        index = {candidate.id: candidate for candidate in candidates}
        for link in response.get("links", []):
            ids = [item for item in link.get("ids", []) if item in index]
            if len(ids) < 2:
                continue
            linked = [index[item] for item in ids]
            if max(item.start for item in linked) - min(item.end for item in linked) > self.config.story_max_gap_seconds:
                continue
            reason = str(link.get("reason", ""))[:700]
            upgrade = str(link.get("upgrade_to", "B"))
            for item in linked:
                item.related_ids = sorted(set(item.related_ids + [other for other in ids if other != item.id]))
                if reason and reason not in item.why_good:
                    item.why_good = f"{item.why_good} História relacionada: {reason}".strip()
                if GRADE_ORDER.get(upgrade, 0) > GRADE_ORDER.get(item.grade, 0):
                    item.grade = upgrade
        return candidates
