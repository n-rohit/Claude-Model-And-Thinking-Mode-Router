#!/usr/bin/env python3
"""
Model Router — decides which Claude model to use for a given prompt
(and optional reference documents), using local rules + local embeddings,
falling back to a local offline LLM (Ollama) only for ambiguous cases.

No network calls to Anthropic are made — this only produces a
recommendation for you to use in Claude Chat.

Usage:
    python main.py --prompt path/to/prompt.txt [--docs path/to/docs_folder]
    python main.py                              # prompts interactively
"""
from __future__ import annotations

# Silences urllib3's NotOpenSSLWarning, which fires on some macOS Python
# installs (system Python is linked against LibreSSL, not OpenSSL). It's
# purely informational and irrelevant here — every request this script
# makes is to plain http://localhost (Ollama), never https, so no TLS/SSL
# behavior is actually involved. Must be set before `requests` (and so
# urllib3) gets imported anywhere below, since the warning fires at
# urllib3's import time, not at request time.
import warnings
warnings.filterwarnings("ignore", message=r"urllib3 v2 only supports OpenSSL")

import argparse
import datetime
import difflib
import json
import os
import sys

import yaml

from router.parse import parse_input
from router.features import extract_features
from router.rules import apply_rules
from router.semantic import SemanticScorer
from router.tiebreak import run_tiebreak
from router.effort import suggest_effort

CONFIG_PATH_DEFAULT = os.path.join(os.path.dirname(__file__), "config.yaml")


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_path(raw: str) -> str:
    """Expand ~ and normalize a user-supplied path. Used for every path,
    whether it came from --prompt/--docs or the interactive prompt, so
    what actually gets opened is always shown back to the user."""
    return os.path.normpath(os.path.expanduser(raw.strip().strip('"').strip("'")))


def prompt_for_path(label: str, required: bool) -> str | None:
    suffix = "" if required else " (leave blank to skip)"
    while True:
        raw = input(f"Enter path to {label}{suffix}: ")
        if not raw.strip():
            if not required:
                return None
            print("This is required — please enter a path.")
            continue
        resolved = resolve_path(raw)
        print(f"  -> using: {resolved}")
        return resolved


def suggest_close_matches(missing_path: str) -> None:
    """When a file isn't found, show what's actually in that directory and
    the closest-matching filenames — catches corrupted/typo'd paths
    immediately instead of leaving it a mystery."""
    parent = os.path.dirname(missing_path) or "."
    target_name = os.path.basename(missing_path)
    print(f"  Looked for exactly: {missing_path!r}", file=sys.stderr)
    if not os.path.isdir(parent):
        print(f"  The folder itself doesn't exist: {parent}", file=sys.stderr)
        return
    entries = os.listdir(parent)
    matches = difflib.get_close_matches(target_name, entries, n=3, cutoff=0.5)
    if matches:
        print(f"  Did you mean one of these (in {parent}):", file=sys.stderr)
        for m in matches:
            print(f"    - {m}", file=sys.stderr)
    else:
        print(f"  Contents of {parent}:", file=sys.stderr)
        for e in sorted(entries)[:20]:
            print(f"    - {e}", file=sys.stderr)


def log_decision(log_file: str, record: dict) -> None:
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        pass  # logging failures shouldn't break the CLI


def print_field(label: str, value: str, width: int = 18) -> None:
    print(f"{label:<{width}} : {value}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Recommend which Claude model to use for a prompt.")
    parser.add_argument("--prompt", help="Path to the prompt Markdown file.")
    parser.add_argument("--docs", help="Path to a document file or folder of Markdown documents.")
    parser.add_argument("--config", default=CONFIG_PATH_DEFAULT, help="Path to config.yaml.")
    args = parser.parse_args()

    config = load_config(args.config)

    interactive = sys.stdin.isatty()

    if args.prompt:
        prompt_path = resolve_path(args.prompt)
        print(f"Using prompt file: {prompt_path}")
    elif interactive:
        prompt_path = prompt_for_path("your prompt file (.txt or .md)", required=True)
    else:
        parser.error("--prompt is required when not running in an interactive terminal.")

    if args.docs is not None:
        docs_path = resolve_path(args.docs) if args.docs else None
        if docs_path:
            print(f"Using docs path: {docs_path}")
    elif interactive:
        docs_path = prompt_for_path("a documents file/folder", required=False)
    else:
        docs_path = None

    parsed = parse_input(prompt_path, docs_path)
    features = extract_features(parsed, config["keywords"])

    rule_decision = apply_rules(features, config["rules"])

    # Only ever populated when Ollama itself returned a real, successful
    # prediction — this is what actually gets displayed as "Confidence".
    llm_confidence: float | None = None
    semantic_gap_internal: float | None = None  # used for the escalation decision only, never shown
    llm_effort: str | None = None  # only set when tiebreak-llm succeeds and gave a usable effort

    if rule_decision is not None:
        tier = rule_decision.tier
        reason = rule_decision.reason
        method = "rule"
    else:
        scorer = SemanticScorer(
            embedding_model=config["semantic"]["embedding_model"],
            exemplars_file=os.path.join(os.path.dirname(__file__), config["semantic"]["exemplars_file"]),
        )
        semantic_result = scorer.score(
            parsed.prompt_text, max_chars=config["semantic"]["max_chars_embedded"]
        )
        semantic_gap_internal = semantic_result.confidence_gap

        if semantic_result.confidence_gap >= config["semantic"]["confidence_gap_threshold"]:
            tier = semantic_result.top_tier
            reason = f"Semantic match to '{tier}' exemplars."
            method = "semantic"
        else:
            doc_summaries = [
                f"{os.path.basename(d.path)} (~{len(d.text.split())} words)" for d in parsed.documents
            ]
            tiebreak_result = run_tiebreak(
                parsed.prompt_text, doc_summaries, config["tiebreak"], config["effort"]
            )
            tier = tiebreak_result.tier
            reason = tiebreak_result.reason
            if tiebreak_result.used_fallback:
                method = "tiebreak-fallback"
            else:
                method = "tiebreak-llm"
                llm_confidence = tiebreak_result.confidence
                llm_effort = tiebreak_result.effort

    model = config["tiers"][tier]

    # Effort: use the LLM's own judgment when we have one (tiebreak-llm),
    # otherwise fall back to the feature-based heuristic — same heuristic
    # for rule/semantic/tiebreak-fallback, so every path always has one.
    effort = llm_effort if llm_effort is not None else suggest_effort(features, config["effort"], tier)

    print("\n" + "=" * 60)
    print_field("Recommended model", model)
    print_field("Thinking level", effort)
    print_field("Decided by", method)
    if method == "tiebreak-llm" and llm_confidence is not None:
        print_field("Confidence", f"{llm_confidence:.2f}%")
    print_field("Reason", reason)
    print("=" * 60)
    print(
        f"(prompt: {features.word_count} words, {features.doc_count} docs, "
        f"{features.code_fence_count} code blocks)"
    )

    log_decision(
        config["logging"]["log_file"],
        {
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "prompt_path": prompt_path,
            "docs_path": docs_path,
            "tier": tier,
            "model": model,
            "effort": effort,
            "effort_source": "llm" if llm_effort is not None else "heuristic",
            "method": method,
            "reason": reason,
            "llm_confidence": llm_confidence,
            "semantic_confidence_gap": semantic_gap_internal,
            "features": features.as_dict(),
        },
    )


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        missing = str(exc).split(": ", 1)[-1]
        suggest_close_matches(missing)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(130)
