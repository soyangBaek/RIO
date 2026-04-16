"""Intent parser unit tests."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from app.domains.speech.intent_parser import IntentParser, aliases_from_triggers_yaml  # noqa: E402


ALIASES = {
    "camera.capture": ["사진 찍어줘", "photo"],
    "smarthome.aircon.on": ["에어컨 켜줘"],
    "weather.current": ["날씨 알려줘"],
    "system.cancel": ["취소"],
}


def test_exact_match():
    p = IntentParser(ALIASES)
    r = p.parse("사진 찍어줘", stt_confidence=1.0)
    assert r is not None and r.intent_id == "camera.capture"
    assert r.match_confidence == 1.0


def test_case_and_punctuation_insensitive():
    p = IntentParser(ALIASES)
    r = p.parse("Photo!")
    assert r is not None and r.intent_id == "camera.capture"


def test_fuzzy_via_token_containment():
    p = IntentParser(ALIASES)
    r = p.parse("에어컨 좀 켜줘", stt_confidence=0.9)
    assert r is not None and r.intent_id == "smarthome.aircon.on"


def test_below_threshold_returns_none():
    p = IntentParser(ALIASES, min_confidence=0.8)
    assert p.parse("냉장고 문 열어") is None


def test_empty_input_returns_none():
    p = IntentParser(ALIASES)
    assert p.parse("") is None


def test_aliases_loader_filters_empty_and_pattern_only():
    table = aliases_from_triggers_yaml({
        "a": ["x"],
        "b": {"aliases": ["y"]},
        "c": {"patterns": ["{duration}"]},
    })
    assert table == {"a": ["x"], "b": ["y"]}


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok:", name)
