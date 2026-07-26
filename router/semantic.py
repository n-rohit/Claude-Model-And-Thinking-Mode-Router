"""
Local, offline semantic scoring. Embeds the prompt text with a small
CPU-friendly model (via fastembed — no PyTorch, no GPU needed) and compares
it against a curated set of tier-labeled exemplar prompts.

Only the prompt text is embedded, not full document bodies — document
*volume* is already handled by the rule layer. This keeps embedding fast
and keeps the comparison focused on "what kind of task is this."
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np
import yaml


@dataclass
class SemanticResult:
    top_tier: str
    confidence_gap: float
    scores: Dict[str, float]


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


class SemanticScorer:
    def __init__(self, embedding_model: str, exemplars_file: str):
        # Imported lazily so the rest of the CLI still works (e.g. --help,
        # or pure rule-layer decisions) even if fastembed isn't installed yet.
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=embedding_model)

        with open(exemplars_file, "r", encoding="utf-8") as f:
            self._exemplars: Dict[str, List[str]] = yaml.safe_load(f)

        self._exemplar_embeddings: Dict[str, List[np.ndarray]] = {}
        for tier, examples in self._exemplars.items():
            self._exemplar_embeddings[tier] = list(self._model.embed(examples))

    def score(self, text: str, max_chars: int = 2000) -> SemanticResult:
        snippet = text[:max_chars]
        query_embedding = list(self._model.embed([snippet]))[0]

        tier_scores: Dict[str, float] = {}
        for tier, embeddings in self._exemplar_embeddings.items():
            sims = [_cosine_sim(query_embedding, emb) for emb in embeddings]
            tier_scores[tier] = max(sims) if sims else 0.0

        ranked = sorted(tier_scores.items(), key=lambda kv: kv[1], reverse=True)
        top_tier, top_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0

        return SemanticResult(
            top_tier=top_tier,
            confidence_gap=top_score - second_score,
            scores=tier_scores,
        )
