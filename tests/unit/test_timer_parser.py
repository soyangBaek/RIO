"""Timer parser unit tests."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from app.domains.speech.timer_parser import parse_duration  # noqa: E402


def test_korean_digits():
    assert parse_duration("5분 있다 알려줘") == 300
    assert parse_duration("30초 뒤") == 30
    assert parse_duration("1시간 30분") == 5400
    assert parse_duration("2시간") == 7200


def test_korean_word_numerals():
    assert parse_duration("다섯 분 있다") == 300
    assert parse_duration("한 시간") == 3600


def test_half_expression():
    assert parse_duration("1시간 반") == 5400


def test_english_forms():
    assert parse_duration("in 10 minutes") == 600
    assert parse_duration("30 seconds") == 30
    assert parse_duration("2 hours 15 min") == 8100


def test_rejection_cases():
    assert parse_duration("") is None
    assert parse_duration("내일 알려줘") is None
    assert parse_duration("0분") is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
