"""
Offline LLM tiebreaker — only invoked when the rule layer didn't fire and
the semantic layer wasn't confident enough to trust on its own.

Calls a local Ollama model and asks for a short, strict-JSON verdict,
including the model's own self-reported confidence. If Ollama isn't
running or errors out, falls back to a configured default tier rather
than crashing the CLI.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Dict, List

import requests

from router.effort import VALID_EFFORTS, cap_effort

VALID_TIERS = {"haiku", "sonnet", "opus", "fable"}

SYSTEM_PROMPT = """You are a routing assistant. You will be shown a task \
(a prompt, possibly with reference documents) and must classify how much \
reasoning capability it needs. Respond with ONLY a JSON object, no other \
text, in exactly this form:

{"tier": "haiku|sonnet|opus|fable", "confidence": <integer 0-100>, "effort": "low|medium|high|xhigh", "reason": "one short sentence"}

"confidence" is how sure YOU are that this is the right tier — 0 means a
coin flip, 100 means certain. Give your honest assessment, not always a
high number.

"effort" is a SEPARATE decision from tier — how much internal reasoning
depth the chosen model should use for this specific task:
- "low": simple/mechanical even for this tier, a quick response is fine.
- "medium": typical depth for this kind of task.
- "high": benefits from careful, thorough reasoning.
- "xhigh": only for genuinely hard coding/agentic work needing extended
exploration — use rarely, and never for a "haiku" tier task.

Guidance:
- "haiku": simple, short, mechanical tasks (formatting, short lookups, \
small rewrites).
- "sonnet": everyday reasoning, writing, coding, explanation tasks of \
moderate length.
- "opus": long or complex tasks — multi-document synthesis, deep \
reasoning, large-scale code changes, high-stakes analysis.
- "fable": reserve this ONLY for tasks that go clearly beyond even "opus" \
— genuinely extreme scope or stakes, such as multi-jurisdiction \
regulatory work, board- or regulator-facing deliverables with no room \
for error, or synthesis across years of records/many documents at once. \
Most tasks, even hard ones, are NOT this tier — use it rarely.
"""


@dataclass
class TiebreakResult:
    tier: str
    reason: str
    used_fallback: bool
    confidence: float | None = None  # 0-100, self-reported by the LLM; None on fallback
    effort: str | None = None  # low/medium/high/xhigh, self-reported by the LLM; None on fallback


def _build_user_prompt(prompt_text: str, doc_summaries: List[str], max_chars: int) -> str:
    text = prompt_text[:max_chars]
    parts = [f"PROMPT:\n{text}"]
    if doc_summaries:
        joined = "\n".join(f"- {d}" for d in doc_summaries)
        parts.append(f"\nATTACHED DOCUMENTS ({len(doc_summaries)}):\n{joined}")
    return "\n".join(parts)


def _extract_json(raw: str) -> Dict:
    # Models occasionally wrap JSON in prose or code fences despite
    # instructions — pull out the first {...} block defensively.
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in model output: {raw!r}")
    return json.loads(match.group(0))


def run_tiebreak(
    prompt_text: str,
    doc_summaries: List[str],
    cfg: Dict,
    effort_cfg: Dict,
) -> TiebreakResult:
    fallback_tier = cfg.get("fallback_tier", "sonnet")

    if not cfg.get("enabled", True):
        return TiebreakResult(tier=fallback_tier, reason="Tiebreak disabled in config.", used_fallback=True)

    user_prompt = _build_user_prompt(prompt_text, doc_summaries, max_chars=3000)

    try:
        response = requests.post(
            f"{cfg['ollama_host']}/api/generate",
            json={
                "model": cfg["model"],
                "system": SYSTEM_PROMPT,
                "prompt": user_prompt,
                "stream": False,
            },
            timeout=cfg.get("timeout_seconds", 30),
        )
        response.raise_for_status()
        raw_text = response.json().get("response", "")
        parsed = _extract_json(raw_text)

        tier = str(parsed.get("tier", "")).strip().lower()
        reason = str(parsed.get("reason", "")).strip() or "No reason given by tiebreaker."

        raw_confidence = parsed.get("confidence")
        confidence: float | None = None
        if isinstance(raw_confidence, (int, float)) and not isinstance(raw_confidence, bool):
            confidence = max(0.0, min(100.0, float(raw_confidence)))

        raw_effort = str(parsed.get("effort", "")).strip().lower()
        effort: str | None = raw_effort if raw_effort in VALID_EFFORTS else None

        if tier not in VALID_TIERS:
            raise ValueError(f"Model returned an invalid tier: {tier!r}")

        if effort is not None:
            effort = cap_effort(effort, tier, effort_cfg)

        return TiebreakResult(
            tier=tier, reason=reason, used_fallback=False, confidence=confidence, effort=effort
        )

    except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
        return TiebreakResult(
            tier=fallback_tier,
            reason=f"Tiebreaker unavailable ({exc.__class__.__name__}: {exc}); used fallback tier.",
            used_fallback=True,
        )
