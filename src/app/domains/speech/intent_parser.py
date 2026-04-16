"""Canonical intent resolver (rule-based, no LLM).

Given an STT transcript, this parser tries to match the text against the
alias table produced from ``configs/triggers.yaml`` and returns the
best-scoring canonical intent id. Timer creation (``timer.create``) carries
a duration slot that is filled by :mod:`timer_parser`; this parser only
decides *which* intent matched.

Matching strategy:

1. Normalise input (lowercase, strip punctuation, collapse whitespace).
2. Exact match against any alias → confidence = 1.0.
3. Fuzzy similarity via :class:`difflib.SequenceMatcher` (stdlib, no extra
   dependency). Best score across all aliases wins.
4. Reject anything below ``min_confidence`` — the audio worker then
   publishes ``voice.intent.unknown`` so a confused oneshot fires.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple


_PUNCT_RE = re.compile(r"[.,!?;:\"'`~]+")
_WS_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    if not text:
        return ""
    text = text.strip().lower()
    text = _PUNCT_RE.sub("", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


@dataclass(frozen=True)
class ParseResult:
    intent_id: str
    alias_matched: str
    match_confidence: float        # 0..1 similarity
    combined_confidence: float     # match × stt


class IntentParser:
    def __init__(
        self,
        aliases: Dict[str, List[str]],
        min_confidence: float = 0.6,
    ) -> None:
        self._min_conf = min_confidence
        # Precompute normalised alias table for speed and determinism.
        self._table: List[Tuple[str, str, str]] = []  # (normalised, original, intent)
        for intent_id, al_list in aliases.items():
            for alias in al_list:
                self._table.append((normalize(alias), alias, intent_id))

    @property
    def min_confidence(self) -> float:
        return self._min_conf

    def parse(self, text: str, stt_confidence: float = 1.0) -> Optional[ParseResult]:
        target = normalize(text)
        if not target:
            return None

        # Exact match short-circuit.
        for norm, original, intent_id in self._table:
            if norm == target:
                return ParseResult(
                    intent_id=intent_id,
                    alias_matched=original,
                    match_confidence=1.0,
                    combined_confidence=min(1.0, 1.0 * stt_confidence),
                )

        # Fuzzy: pick the highest SequenceMatcher ratio.
        best_score = 0.0
        best_intent = ""
        best_alias = ""
        for norm, original, intent_id in self._table:
            score = difflib.SequenceMatcher(a=target, b=norm).ratio()
            # Token-containment bonus: "에어컨 좀 켜줘" should match "에어컨 켜줘"
            # even if string ratio is modest. If every token of the alias
            # appears in the target (in order is not required) we nudge the
            # score up toward the alias's length density.
            if score < 0.99:
                alias_tokens = norm.split()
                target_tokens = target.split()
                if alias_tokens and all(tok in target_tokens for tok in alias_tokens):
                    bonus = 0.2 + 0.1 * (len(alias_tokens) / max(1, len(target_tokens)))
                    score = min(0.99, max(score, 0.7 + bonus))
            if score > best_score:
                best_score = score
                best_intent = intent_id
                best_alias = original

        if best_score < self._min_conf:
            return None
        return ParseResult(
            intent_id=best_intent,
            alias_matched=best_alias,
            match_confidence=best_score,
            combined_confidence=min(1.0, best_score * stt_confidence),
        )


def aliases_from_triggers_yaml(data: dict) -> Dict[str, List[str]]:
    """Flatten the ``configs/triggers.yaml`` structure into the parser table.

    Accepted shapes per intent: a bare list of aliases, or a dict with an
    ``aliases`` key (and optional ``patterns`` list that this parser
    ignores — see :mod:`timer_parser`).
    """
    out: Dict[str, List[str]] = {}
    for intent_id, entry in data.items():
        if isinstance(entry, list):
            out[intent_id] = [str(x) for x in entry if x]
        elif isinstance(entry, dict):
            al = entry.get("aliases") or []
            if isinstance(al, list) and al:
                out[intent_id] = [str(x) for x in al if x]
    return out
