"""T-027: Timer parser – 자연어 시간 파싱.

"5분 타이머", "30초 후 알려줘" → duration_ms + label.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

# 시간 패턴 정규식
_PATTERNS = [
    # "N분 M초", "N분", "M초"
    (re.compile(r"(\d+)\s*분\s*(\d+)\s*초"), lambda m: int(m.group(1)) * 60_000 + int(m.group(2)) * 1_000),
    (re.compile(r"(\d+)\s*분"), lambda m: int(m.group(1)) * 60_000),
    (re.compile(r"(\d+)\s*초"), lambda m: int(m.group(1)) * 1_000),
    # "N시간 M분"
    (re.compile(r"(\d+)\s*시간\s*(\d+)\s*분"), lambda m: int(m.group(1)) * 3_600_000 + int(m.group(2)) * 60_000),
    (re.compile(r"(\d+)\s*시간"), lambda m: int(m.group(1)) * 3_600_000),
    # English: "Nm", "Ns", "Nh", "N minutes", "N seconds"
    (re.compile(r"(\d+)\s*(?:minutes?|mins?)"), lambda m: int(m.group(1)) * 60_000),
    (re.compile(r"(\d+)\s*(?:seconds?|secs?)"), lambda m: int(m.group(1)) * 1_000),
    (re.compile(r"(\d+)\s*(?:hours?|hrs?)"), lambda m: int(m.group(1)) * 3_600_000),
]


class TimerParser:
    """자연어에서 타이머 시간을 추출."""

    def parse(self, text: str) -> Tuple[Optional[int], str]:
        """텍스트에서 시간 추출.

        Returns: (duration_ms_or_None, label)
        """
        if not text:
            return None, ""

        for pattern, extractor in _PATTERNS:
            match = pattern.search(text)
            if match:
                duration_ms = extractor(match)
                label = text.strip()
                return duration_ms, label

        return None, text.strip()

    def format_duration(self, duration_ms: int) -> str:
        """ms → 사람 읽기 좋은 문자열."""
        total_sec = duration_ms // 1000
        if total_sec < 60:
            return f"{total_sec}초"
        minutes = total_sec // 60
        seconds = total_sec % 60
        if seconds == 0:
            return f"{minutes}분"
        return f"{minutes}분 {seconds}초"
