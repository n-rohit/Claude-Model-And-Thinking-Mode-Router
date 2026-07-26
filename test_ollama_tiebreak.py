#!/usr/bin/env python3
"""
Standalone Ollama tiebreak test.

This bypasses the rule layer and semantic layer completely and sends
each scenario straight to the local Ollama model (router/tiebreak.py),
exactly as if every case had landed in the "ambiguous" bucket. Use this
to sanity-check the tiebreaker's judgment on its own, independent of the
rest of the pipeline — one realistic scenario per tier.

Requires Ollama running locally with the model set in config.yaml
(default: phi4-mini). If Ollama isn't reachable, each result will show
the fallback tier instead of a real verdict — that's expected, not a bug.

Run:
    python test_ollama_tiebreak.py
"""
from __future__ import annotations

import os

import yaml

from router.tiebreak import run_tiebreak

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")

# One real-world scenario per tier. Each is written the way someone would
# actually type it into Claude Chat — plain sentences, no headers.
SCENARIOS = {
    "expected: haiku": (
        "Our client asked us to change the color of the 'Submit' button "
        "on the invoice approval screen from blue to green, to match "
        "their brand guidelines. Can you make that one CSS change?"
    ),
    "expected: sonnet": (
        "One of our implementation clients is confused about how the "
        "automated bank reconciliation matching works in their new ERP "
        "module. Can you write them a clear explanation, in plain "
        "non-technical language, of how the system matches bank "
        "statement lines to ledger entries, what happens when there's "
        "no match, and how they can review flagged items before "
        "month-end close?"
    ),
    "expected: opus": (
        "We're onboarding a new banking client and need to migrate their "
        "entire chart of accounts, GL entry flows, and reconciliation "
        "rules from their legacy on-premise system into our ERP. Design "
        "the end-to-end migration approach: how we'll map their existing "
        "account structure to ours, how we handle historical transaction "
        "data without breaking audit trails, what validation checks run "
        "before cutover, and a rollback plan if the migration needs to "
        "be aborted mid-way. This needs to hold up under a regulator's "
        "audit later, so the reasoning needs to be thorough."
    ),
    "expected: fable": (
        "Our client's board wants a definitive analysis of our compliance "
        "posture across all the countries they operate in before they'll "
        "approve next quarter's expansion budget. Each country's central "
        "bank has different reporting rules, and this needs to be solid "
        "enough to present directly in the board meeting without caveats."
    ),
}


def main() -> None:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    tiebreak_cfg = config["tiebreak"]
    effort_cfg = config["effort"]
    print(f"Using Ollama model: {tiebreak_cfg['model']} at {tiebreak_cfg['ollama_host']}\n")

    for label, prompt in SCENARIOS.items():
        result = run_tiebreak(prompt, doc_summaries=[], cfg=tiebreak_cfg, effort_cfg=effort_cfg)
        print(f"--- {label} ---")
        print(f"Ollama's tier : {result.tier}")
        print(f"Effort        : {result.effort}")
        print(f"Confidence    : {result.confidence}")
        print(f"Fallback used : {result.used_fallback}")
        print(f"Reason        : {result.reason}")
        print()


if __name__ == "__main__":
    main()
