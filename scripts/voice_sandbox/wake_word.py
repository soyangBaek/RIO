"""Wake word 감지: ASR 텍스트 기반 매칭 + AWAKE 상태/listen_window 관리."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional


@dataclass
class WakeConfig:
    phrase: str
    aliases: list[str]
    fuzzy: bool
    max_edit_distance: int
    cooldown_ms: int
    listen_window_ms: int
    extend_on_command: bool
    min_asr_logprob: float
    strip_from_command: bool


class WakeState(str, Enum):
    ASLEEP = "ASLEEP"
    AWAKE = "AWAKE"


@dataclass
class WakeDecision:
    label: str  # "wake" | "wake+cmd" | "cmd" | "ignored" | "reject_logprob"
    wake_hit: bool
    command: Optional[str]
    matched_alias: Optional[str]
    edit_distance: Optional[int]
    state_before: str
    state_after: str


_TOKEN_SPLIT_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\uac00-\ud7a3\s]")


def _normalize(text: str) -> str:
    t = text.lower()
    t = _PUNCT_RE.sub(" ", t)
    t = _TOKEN_SPLIT_RE.sub(" ", t).strip()
    return t


def _edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            curr[j] = min(
                prev[j] + 1,        # deletion
                curr[j - 1] + 1,    # insertion
                prev[j - 1] + (ca != cb),  # substitution
            )
        prev = curr
    return prev[-1]


class WakeWordDetector:
    def __init__(self, cfg: WakeConfig):
        self.cfg = cfg
        self.state = WakeState.ASLEEP
        self._last_wake_ms: Optional[float] = None
        self._window_ends_at_ms: Optional[float] = None
        self._normalized_aliases = [_normalize(a) for a in cfg.aliases]

    @staticmethod
    def _now_ms() -> float:
        return time.monotonic() * 1000

    def _expire_window_if_needed(self) -> None:
        if self.state == WakeState.AWAKE and self._window_ends_at_ms is not None:
            if self._now_ms() > self._window_ends_at_ms:
                self.state = WakeState.ASLEEP
                self._window_ends_at_ms = None

    def _match_wake_token(self, normalized: str) -> tuple[Optional[str], Optional[int], Optional[int]]:
        """토큰 단위로 wake alias 매칭. (matched_alias, edit_distance, token_index) 반환."""
        tokens = normalized.split()
        best: Optional[tuple[str, int, int]] = None
        for i, tok in enumerate(tokens):
            for alias_raw, alias_norm in zip(self.cfg.aliases, self._normalized_aliases):
                if tok == alias_norm:
                    return alias_raw, 0, i
                if self.cfg.fuzzy:
                    d = _edit_distance(tok, alias_norm)
                    if d <= self.cfg.max_edit_distance and (best is None or d < best[1]):
                        best = (alias_raw, d, i)
        if best is not None:
            return best
        return None, None, None

    @staticmethod
    def _strip_token_at(normalized: str, token_idx: int) -> str:
        tokens = normalized.split()
        if 0 <= token_idx < len(tokens):
            tokens.pop(token_idx)
        return " ".join(tokens).strip()

    def decide(self, asr_text: str, asr_logprob: float) -> WakeDecision:
        self._expire_window_if_needed()
        state_before = self.state.value

        if asr_logprob < self.cfg.min_asr_logprob:
            return WakeDecision(
                label="reject_logprob",
                wake_hit=False,
                command=None,
                matched_alias=None,
                edit_distance=None,
                state_before=state_before,
                state_after=self.state.value,
            )

        normalized = _normalize(asr_text)
        if not normalized:
            return WakeDecision(
                label="ignored",
                wake_hit=False,
                command=None,
                matched_alias=None,
                edit_distance=None,
                state_before=state_before,
                state_after=self.state.value,
            )

        alias, dist, tok_idx = self._match_wake_token(normalized)

        if alias is not None:
            in_cooldown = (
                self._last_wake_ms is not None
                and (self._now_ms() - self._last_wake_ms) < self.cfg.cooldown_ms
            )
            if not in_cooldown:
                self._last_wake_ms = self._now_ms()
                self.state = WakeState.AWAKE
                self._window_ends_at_ms = self._now_ms() + self.cfg.listen_window_ms

                remainder = (
                    self._strip_token_at(normalized, tok_idx)
                    if self.cfg.strip_from_command and tok_idx is not None
                    else normalized
                )
                if remainder:
                    return WakeDecision(
                        label="wake+cmd",
                        wake_hit=True,
                        command=remainder,
                        matched_alias=alias,
                        edit_distance=dist,
                        state_before=state_before,
                        state_after=self.state.value,
                    )
                return WakeDecision(
                    label="wake",
                    wake_hit=True,
                    command=None,
                    matched_alias=alias,
                    edit_distance=dist,
                    state_before=state_before,
                    state_after=self.state.value,
                )
            # cooldown 중인 wake 는 무시하고 아래 일반 처리로 폴백

        if self.state == WakeState.AWAKE:
            if self.cfg.extend_on_command:
                self._window_ends_at_ms = self._now_ms() + self.cfg.listen_window_ms
            return WakeDecision(
                label="cmd",
                wake_hit=False,
                command=normalized,
                matched_alias=None,
                edit_distance=None,
                state_before=state_before,
                state_after=self.state.value,
            )

        return WakeDecision(
            label="ignored",
            wake_hit=False,
            command=None,
            matched_alias=None,
            edit_distance=None,
            state_before=state_before,
            state_after=self.state.value,
        )
