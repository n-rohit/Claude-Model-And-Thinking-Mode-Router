"""
Hard, deterministic overrides for the unambiguous cases. If a rule fires,
we skip the (slower) semantic and tiebreak layers entirely.

Returns None when no rule confidently applies — that's the signal to fall
through to the semantic layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from router.features import Features


@dataclass
class RuleDecision:
    tier: str
    reason: str


def apply_rules(features: Features, rules_cfg: Dict) -> Optional[RuleDecision]:
    # --- Fable overrides (checked first — the most extreme case) ---
    if features.word_count >= rules_cfg["fable_min_words"]:
        return RuleDecision(
            tier="fable",
            reason=f"Combined text is {features.word_count} words "
                    f"(>= {rules_cfg['fable_min_words']} fable threshold).",
        )
    if features.doc_count >= rules_cfg["fable_min_docs"]:
        return RuleDecision(
            tier="fable",
            reason=f"{features.doc_count} documents attached "
                    f"(>= {rules_cfg['fable_min_docs']} fable threshold).",
        )
    if features.code_fence_count >= rules_cfg["fable_min_code_fences"]:
        return RuleDecision(
            tier="fable",
            reason=f"{features.code_fence_count} code blocks detected "
                    f"(>= {rules_cfg['fable_min_code_fences']} fable threshold).",
        )
    if features.matched_fable_keywords:
        return RuleDecision(
            tier="fable",
            reason=f"Fable-signal keywords detected: {', '.join(features.matched_fable_keywords)}.",
        )

    # --- Heavy/opus overrides ------------------------------------
    if features.word_count >= rules_cfg["opus_min_words"]:
        return RuleDecision(
            tier="opus",
            reason=f"Combined text is {features.word_count} words "
                    f"(>= {rules_cfg['opus_min_words']} threshold).",
        )
    if features.doc_count >= rules_cfg["opus_min_docs"]:
        return RuleDecision(
            tier="opus",
            reason=f"{features.doc_count} documents attached "
                    f"(>= {rules_cfg['opus_min_docs']} threshold).",
        )
    if features.code_fence_count >= rules_cfg["opus_min_code_fences"]:
        return RuleDecision(
            tier="opus",
            reason=f"{features.code_fence_count} code blocks detected "
                    f"(>= {rules_cfg['opus_min_code_fences']} threshold).",
        )
    if features.matched_heavy_keywords:
        return RuleDecision(
            tier="opus",
            reason=f"Heavy-task keywords detected: {', '.join(features.matched_heavy_keywords)}.",
        )

    # --- Light/haiku overrides ------------------------------------
    if (
        features.word_count <= rules_cfg["haiku_max_words"]
        and features.doc_count <= rules_cfg["haiku_max_docs"]
        and features.code_fence_count == 0
        and not features.matched_heavy_keywords
    ):
        return RuleDecision(
            tier="haiku",
            reason=f"Short prompt ({features.word_count} words), no documents, no code.",
        )

    # A light-task keyword ("quick", "rename", "fix typo"...) is a strong
    # lexical signal even if the prompt runs a bit longer than the plain
    # word-count ceiling above — but still capped, so a long prompt that
    # merely mentions "quick" once doesn't get misrouted.
    if (
        features.matched_light_keywords
        and not features.matched_heavy_keywords
        and features.doc_count <= rules_cfg["haiku_max_docs"]
        and features.code_fence_count == 0
        and features.word_count <= rules_cfg["light_keyword_max_words"]
    ):
        return RuleDecision(
            tier="haiku",
            reason=f"Light-task keyword(s) detected: {', '.join(features.matched_light_keywords)} "
                    f"({features.word_count} words, under the {rules_cfg['light_keyword_max_words']}-word ceiling).",
        )

    # No confident rule fired — hand off to the semantic layer.
    return None
