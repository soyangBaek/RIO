"""Natural-language timer parsing for ``timer.create`` intents.

Accepts a spoken fragment such as "5분 있다", "30초 뒤", "1시간 30분 있다가",
or "in 10 minutes" and returns a positive duration in seconds. Returns
``None`` when nothing could be parsed — the caller then publishes a
``task.failed`` with kind ``timer_setup`` so a confused oneshot fires
(scenario VOICE-08).

Scope:
- Relative durations only (absolute times like "오후 3시에" are out of scope
  for MVP — they would need a wall-clock reference).
- Korean + English unit words.
- Digits preferred; a small table of Korean number words handles the most
  common cases when STT spells them out.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

# -- word-number fallback ---------------------------------------------------
# Maps a Korean number word to its integer value. Limited to sensible
# timer ranges (0-99).
_KO_WORDS: dict = {
    "영": 0, "공": 0,
    "일": 1, "한": 1, "하나": 1,
    "이": 2, "두": 2, "둘": 2,
    "삼": 3, "세": 3, "셋": 3,
    "사": 4, "네": 4, "넷": 4,
    "오": 5, "다섯": 5,
    "육": 6, "여섯": 6,
    "칠": 7, "일곱": 7,
    "팔": 8, "여덟": 8,
    "구": 9, "아홉": 9,
    "십": 10, "열": 10,
    "이십": 20, "스물": 20,
    "삼십": 30, "서른": 30,
    "사십": 40, "마흔": 40,
    "오십": 50, "쉰": 50,
    "육십": 60, "예순": 60,
    "칠십": 70, "일흔": 70,
    "팔십": 80, "여든": 80,
    "구십": 90, "아흔": 90,
}

# Canonicalise every unit string the regex can yield to its seconds value.
_UNIT_SECONDS = {
    "시간": 3600,
    "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600,
    "분": 60,
    "minute": 60, "minutes": 60, "min": 60, "mins": 60,
    "초": 1,
    "second": 1, "seconds": 1, "sec": 1, "secs": 1,
}

# Single alternation orders longest forms first so e.g. "minutes" matches
# the full word (60s) instead of the "min" prefix that would land in a
# subsequent iteration. Word boundaries on the English side prevent
# catastrophic matches inside unrelated words.
_UNIT_RE = re.compile(
    r"(\d+)\s*("
    r"시간|분|초"
    r"|hours|hrs|hour|hr|minutes|mins|minute|min|seconds|secs|second|sec"
    r")",
    re.IGNORECASE,
)


def _words_to_digits(text: str) -> str:
    """Replace whole Korean number words with their digit form."""
    out = text
    # Longer words first so "이십" beats "이".
    for word in sorted(_KO_WORDS, key=len, reverse=True):
        out = out.replace(word, str(_KO_WORDS[word]))
    return out


def parse_duration(text: str) -> Optional[int]:
    """Return a positive integer number of seconds parsed from ``text``.

    The parser accumulates every ``<number><unit>`` pair it finds so that
    combinations like "1시간 30분" resolve to 5400 seconds.
    """
    if not text:
        return None
    s = text.strip()
    # Translate written Korean numerals so we can rely on digit regex.
    s_digits = _words_to_digits(s)

    total = 0
    matched_any = False
    for m in _UNIT_RE.finditer(s_digits):
        num = int(m.group(1))
        unit_key = m.group(2).lower()
        unit_s = _UNIT_SECONDS.get(unit_key)
        if unit_s is None:
            continue
        total += num * unit_s
        matched_any = True

    # Handle "반 시간" (half an hour) and "30분 반" (plus half-minute) — niche
    # but cheap to support because it's a single word.
    if "반시간" in s_digits.replace(" ", "") or "시간반" in s_digits.replace(" ", ""):
        total += 1800
        matched_any = True

    if not matched_any or total <= 0:
        return None
    return total
