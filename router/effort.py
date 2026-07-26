"""
Suggests an effort level (low/medium/high/xhigh) — a second dimension,
independent from tier. This is a real Claude feature: the same model can
be asked to reason more or less before answering, so two tasks that both
land on "sonnet" don't have to be treated identically. Something that
only marginally needed a heavier tier can instead stay on the lighter
model at higher effort, rather than the tier jumping to absorb it.

Used for the rule, semantic, and tiebreak-fallback paths — anywhere a
live LLM judgment isn't available. When the Ollama tiebreaker succeeds,
its own self-reported effort is used instead (see router/tiebreak.py),
since it can actually reason about the task rather than just count words.

Effort itself doesn't change the "Recommended model" string — it's a
separate setting you choose in Claude Chat (click the model name next to
the send button) or pass as the `effort` API parameter.
"""
from __future__ import annotations

from typing import Dict

from router.features import Features

VALID_EFFORTS = ["low", "medium", "high", "xhigh"]


def suggest_effort(features: Features, cfg: Dict, tier: str) -> str:
    """Feature-based effort heuristic, capped by what the given tier supports."""
    score = 0  # index into VALID_EFFORTS

    if features.word_count >= cfg["xhigh_min_words"]:
        score = max(score, 3)
    elif features.word_count >= cfg["high_min_words"]:
        score = max(score, 2)
    elif features.word_count >= cfg["medium_min_words"]:
        score = max(score, 1)

    if features.list_item_count >= cfg["xhigh_min_list_items"]:
        score = max(score, 3)
    elif features.list_item_count >= cfg["high_min_list_items"]:
        score = max(score, 2)

    if cfg.get("keyword_bump", True) and (
        features.matched_heavy_keywords or features.matched_fable_keywords
    ):
        score = max(score, 2)  # at least "high" if a heavy/fable-signal word matched

    effort = VALID_EFFORTS[score]
    return cap_effort(effort, tier, cfg)


def cap_effort(effort: str, tier: str, cfg: Dict) -> str:
    """xhigh isn't meaningful/available on every tier — cap it down to high
    if the tier doesn't support it. Configurable so this stays accurate as
    Anthropic's effort-level support per model changes."""
    if effort == "xhigh" and tier not in cfg.get("tiers_supporting_xhigh", []):
        return "high"
    return effort
