"""
Extracts lightweight structural signals from the combined prompt + document
text. No ML here — just counting. Cheap and deterministic on purpose, since
this feeds the rule layer that's supposed to catch the "obvious" cases fast.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List

from router.parse import ParsedInput

CODE_FENCE_RE = re.compile(r"```")
TABLE_ROW_RE = re.compile(r"^\s*\|.+\|\s*$", re.MULTILINE)
LINK_RE = re.compile(r"\[[^\]]+\]\([^)]+\)")
HEADER_RE = re.compile(r"^#{1,6}\s+\S", re.MULTILINE)
LIST_ITEM_RE = re.compile(r"^\s*([-*+]|\d+\.)\s+\S", re.MULTILINE)


@dataclass
class Features:
    word_count: int
    token_estimate: int
    doc_count: int
    code_fence_count: int
    table_row_count: int
    link_count: int
    header_count: int
    list_item_count: int
    matched_heavy_keywords: List[str] = field(default_factory=list)
    matched_light_keywords: List[str] = field(default_factory=list)
    matched_fable_keywords: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict:
        return self.__dict__


def _estimate_tokens(word_count: int) -> int:
    # Rough heuristic (~1.3 tokens per word for English text). Good enough
    # for routing decisions — we don't need exact Claude tokenization here.
    return int(word_count * 1.3)


def extract_features(parsed: ParsedInput, keywords: Dict[str, List[str]]) -> Features:
    text = parsed.combined_text
    lower_text = text.lower()

    word_count = len(text.split())
    code_fence_count = len(CODE_FENCE_RE.findall(text)) // 2  # fences come in pairs
    table_row_count = len(TABLE_ROW_RE.findall(text))
    link_count = len(LINK_RE.findall(text))
    header_count = len(HEADER_RE.findall(text))
    list_item_count = len(LIST_ITEM_RE.findall(text))

    heavy_hits = [kw for kw in keywords.get("heavy_task", []) if kw.lower() in lower_text]
    light_hits = [kw for kw in keywords.get("light_task", []) if kw.lower() in lower_text]
    fable_hits = [kw for kw in keywords.get("fable_task", []) if kw.lower() in lower_text]

    return Features(
        word_count=word_count,
        token_estimate=_estimate_tokens(word_count),
        doc_count=parsed.document_count,
        code_fence_count=code_fence_count,
        table_row_count=table_row_count,
        link_count=link_count,
        header_count=header_count,
        list_item_count=list_item_count,
        matched_heavy_keywords=heavy_hits,
        matched_light_keywords=light_hits,
        matched_fable_keywords=fable_hits,
    )
