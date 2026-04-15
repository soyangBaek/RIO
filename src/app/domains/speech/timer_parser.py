from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


@dataclass(slots=True)
class TimerParseResult:
    ok: bool
    payload: dict[str, object] = field(default_factory=dict)
    error: str | None = None


RELATIVE_COMPONENT_PATTERNS = {
    "hours": re.compile(r"(?P<value>\d+)\s*(시간|hours?|hrs?)"),
    "minutes": re.compile(r"(?P<value>\d+)\s*(분|minutes?|mins?)"),
    "seconds": re.compile(r"(?P<value>\d+)\s*(초|seconds?|secs?)"),
}
RELATIVE_HINT = re.compile(r"(뒤|후|있다|later|after|in\s+\d+)")
ABSOLUTE_PATTERN = re.compile(
    r"(?:(?P<meridiem>오전|오후|am|pm)\s*)?(?P<hour>\d{1,2})\s*시(?:\s*(?P<minute>\d{1,2})\s*분?)?(?:\s*(?P<half>반))?"
)


def _relative_seconds(text: str) -> int:
    total = 0
    for unit, pattern in RELATIVE_COMPONENT_PATTERNS.items():
        for match in pattern.finditer(text):
            value = int(match.group("value"))
            if unit == "hours":
                total += value * 3600
            elif unit == "minutes":
                total += value * 60
            else:
                total += value
    return total


def _parse_absolute(text: str, now: datetime) -> datetime | None:
    match = ABSOLUTE_PATTERN.search(text)
    if match is None:
        return None
    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    if match.group("half"):
        minute = 30
    meridiem = (match.group("meridiem") or "").lower()
    if meridiem in {"오후", "pm"} and hour < 12:
        hour += 12
    if meridiem in {"오전", "am"} and hour == 12:
        hour = 0
    target = now.replace(hour=hour % 24, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def parse_timer_text(text: str, *, now: datetime | None = None) -> TimerParseResult:
    now = now or datetime.now(timezone.utc)
    cleaned = text.strip().lower()
    relative_seconds = _relative_seconds(cleaned)
    if relative_seconds > 0 and RELATIVE_HINT.search(cleaned):
        due_at = now + timedelta(seconds=relative_seconds)
        return TimerParseResult(
            ok=True,
            payload={
                "intent": "timer.create",
                "timer_id": str(uuid.uuid4()),
                "delay_seconds": relative_seconds,
                "due_at": due_at.isoformat(),
                "spoken_text": text,
            },
        )

    absolute_due = _parse_absolute(cleaned, now)
    if absolute_due is not None:
        delay_seconds = int((absolute_due - now).total_seconds())
        return TimerParseResult(
            ok=True,
            payload={
                "intent": "timer.create",
                "timer_id": str(uuid.uuid4()),
                "delay_seconds": delay_seconds,
                "due_at": absolute_due.isoformat(),
                "spoken_text": text,
            },
        )

    return TimerParseResult(ok=False, error="timer_parse_failed")
