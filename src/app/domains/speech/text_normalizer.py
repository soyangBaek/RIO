from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
import re


@dataclass(slots=True)
class TextNormalizationResult:
    original_text: str
    normalized_text: str
    replacements: list[dict[str, object]] = field(default_factory=list)


class KoreanCommandNormalizer:
    _CHO = (
        "ㄱ",
        "ㄲ",
        "ㄴ",
        "ㄷ",
        "ㄸ",
        "ㄹ",
        "ㅁ",
        "ㅂ",
        "ㅃ",
        "ㅅ",
        "ㅆ",
        "ㅇ",
        "ㅈ",
        "ㅉ",
        "ㅊ",
        "ㅋ",
        "ㅌ",
        "ㅍ",
        "ㅎ",
    )
    _JUNG = (
        "ㅏ",
        "ㅐ",
        "ㅑ",
        "ㅒ",
        "ㅓ",
        "ㅔ",
        "ㅕ",
        "ㅖ",
        "ㅗ",
        "ㅘ",
        "ㅙ",
        "ㅚ",
        "ㅛ",
        "ㅜ",
        "ㅝ",
        "ㅞ",
        "ㅟ",
        "ㅠ",
        "ㅡ",
        "ㅢ",
        "ㅣ",
    )
    _JONG = (
        "",
        "ㄱ",
        "ㄲ",
        "ㄳ",
        "ㄴ",
        "ㄵ",
        "ㄶ",
        "ㄷ",
        "ㄹ",
        "ㄺ",
        "ㄻ",
        "ㄼ",
        "ㄽ",
        "ㄾ",
        "ㄿ",
        "ㅀ",
        "ㅁ",
        "ㅂ",
        "ㅄ",
        "ㅅ",
        "ㅆ",
        "ㅇ",
        "ㅈ",
        "ㅊ",
        "ㅋ",
        "ㅌ",
        "ㅍ",
        "ㅎ",
    )

    _REPLACEMENTS: tuple[tuple[str, str], ...] = (
        ("팁이", "티비"),
        ("희비", "티비"),
        ("히비", "티비"),
        ("시비", "티비"),
        ("티브이", "티비"),
        ("애어컨", "에어컨"),
        ("에어콘", "에어컨"),
        ("에아컨", "에어컨"),
        ("청소 키", "청소기"),
        ("로보트", "로봇"),
        ("댄쓰", "댄스"),
        ("댄수", "댄스"),
        ("겜모드", "게임 모드"),
        ("타이머", "타이머"),
        ("알람", "알람"),
        ("켜 줘", "켜줘"),
        ("꺼 줘", "꺼줘"),
        ("틀어 줘", "틀어줘"),
        ("멈춰 줘", "멈춰줘"),
        ("맞춰 줘", "맞춰줘"),
        ("찍어 줘", "찍어줘"),
        ("알려 줘", "알려줘"),
        ("켜죠", "켜줘"),
        ("켜조", "켜줘"),
        ("꺼죠", "꺼줘"),
        ("꺼조", "꺼줘"),
        ("끄죠", "꺼줘"),
        ("끄조", "꺼줘"),
    )
    _ASCII_CANONICAL = {
        "tv": "티비",
        "teevee": "티비",
        "aircon": "에어컨",
        "ac": "에어컨",
        "music": "음악",
        "photo": "사진",
        "timer": "타이머",
        "game": "게임",
        "dance": "댄스",
        "weather": "날씨",
    }
    _FUZZY_CANONICALS: tuple[str, ...] = (
        "티비",
        "텔레비전",
        "에어컨",
        "조명",
        "전등",
        "불",
        "청소기",
        "로봇",
        "음악",
        "노래",
        "댄스",
        "춤춰",
        "게임",
        "사진",
        "날씨",
        "타이머",
        "알람",
        "거실",
        "침실",
        "안방",
        "주방",
        "부엌",
        "켜줘",
        "꺼줘",
        "틀어줘",
        "멈춰줘",
        "맞춰줘",
        "알려줘",
        "찍어줘",
        "재생",
        "시작",
        "실행",
        "취소",
        "확인",
        "켜",
        "꺼",
        "틀어",
        "정지",
    )
    _DEVICE_CANONICALS: tuple[str, ...] = (
        "티비",
        "텔레비전",
        "에어컨",
        "조명",
        "전등",
        "불",
        "청소기",
        "로봇",
        "음악",
        "노래",
        "댄스",
        "게임",
        "사진",
        "날씨",
        "타이머",
        "알람",
    )
    _ACTION_HINTS: tuple[str, ...] = (
        "켜",
        "꺼",
        "끄",
        "틀어",
        "멈춰",
        "정지",
        "재생",
        "시작",
        "실행",
        "맞춰",
        "온도",
        "알려",
        "찍어",
        "모드",
    )
    _ACTION_CANONICALS: tuple[str, ...] = (
        "켜줘",
        "꺼줘",
        "틀어줘",
        "멈춰줘",
        "맞춰줘",
        "알려줘",
        "찍어줘",
        "재생",
        "시작",
        "실행",
        "취소",
        "확인",
        "켜",
        "꺼",
        "틀어",
        "정지",
    )
    _PARTICLES: tuple[str, ...] = (
        "에서",
        "으로",
        "에게",
        "한테",
        "부터",
        "까지",
        "처럼",
        "보다",
        "라도",
        "이면",
        "으면",
        "은",
        "는",
        "이",
        "가",
        "을",
        "를",
        "에",
        "도",
        "만",
        "과",
        "와",
        "랑",
    )

    @classmethod
    def _to_jamo(cls, text: str) -> str:
        parts: list[str] = []
        for char in text:
            code = ord(char)
            if 0xAC00 <= code <= 0xD7A3:
                syllable_index = code - 0xAC00
                cho = syllable_index // 588
                jung = (syllable_index % 588) // 28
                jong = syllable_index % 28
                parts.append(cls._CHO[cho])
                parts.append(cls._JUNG[jung])
                if cls._JONG[jong]:
                    parts.append(cls._JONG[jong])
            else:
                parts.append(char)
        return "".join(parts)

    @classmethod
    def _similarity(cls, a: str, b: str) -> float:
        surface = SequenceMatcher(None, a, b).ratio()
        jamo = SequenceMatcher(None, cls._to_jamo(a), cls._to_jamo(b)).ratio()
        return max(surface, jamo)

    @classmethod
    def _split_particle(cls, token: str) -> tuple[str, str]:
        if len(token) < 3:
            return token, ""
        for particle in cls._PARTICLES:
            if token.endswith(particle) and len(token) - len(particle) >= 2:
                return token[: -len(particle)], particle
        return token, ""

    @classmethod
    def _looks_like_command_context(cls, text: str) -> bool:
        compact = text.replace(" ", "")
        if any(hint in compact for hint in cls._ACTION_HINTS):
            return True
        if any(device in text for device in cls._DEVICE_CANONICALS):
            return True
        if re.search(r"-?\d{1,2}\s*도", text):
            return True
        return False

    @classmethod
    def _fuzzy_best_candidate(cls, token: str, *, command_context: bool) -> tuple[str | None, float]:
        if len(token) < 2:
            return None, 0.0
        if any(char.isdigit() for char in token):
            return None, 0.0

        best_token: str | None = None
        best_score = 0.0
        second_score = 0.0
        for candidate in cls._FUZZY_CANONICALS:
            if abs(len(candidate) - len(token)) > 2:
                continue
            score = cls._similarity(token, candidate)
            if score > best_score:
                second_score = best_score
                best_score = score
                best_token = candidate
            elif score > second_score:
                second_score = score

        if best_token is None:
            return None, 0.0

        threshold = 0.91 if len(token) <= 2 else 0.84
        if command_context and best_token in cls._DEVICE_CANONICALS:
            threshold = 0.87 if len(token) <= 2 else 0.82
        elif command_context and best_token in cls._ACTION_CANONICALS:
            threshold = 0.75 if len(token) <= 4 else 0.78
        margin = 0.06
        if best_score >= threshold and (best_score - second_score) >= margin:
            return best_token, best_score
        return None, best_score

    def normalize(self, text: str) -> TextNormalizationResult:
        lowered = re.sub(r"\s+", " ", text.strip().lower())
        normalized = lowered
        replacements: list[dict[str, object]] = []

        for src, dst in self._REPLACEMENTS:
            if src in normalized:
                count = normalized.count(src)
                normalized = normalized.replace(src, dst)
                replacements.append({"mode": "direct", "from": src, "to": dst, "count": count})

        command_context = self._looks_like_command_context(normalized)
        tokens = re.findall(r"[0-9a-z가-힣]+|[^0-9a-z가-힣]+", normalized)
        corrected_tokens: list[str] = []
        for token in tokens:
            if not re.fullmatch(r"[0-9a-z가-힣]+", token):
                corrected_tokens.append(token)
                continue

            if token in self._ASCII_CANONICAL:
                corrected = self._ASCII_CANONICAL[token]
                corrected_tokens.append(corrected)
                replacements.append({"mode": "ascii", "from": token, "to": corrected, "score": 1.0})
                continue

            base, suffix = self._split_particle(token)
            candidate, score = self._fuzzy_best_candidate(base, command_context=command_context)
            if candidate is not None and candidate != base:
                corrected = candidate + suffix
                corrected_tokens.append(corrected)
                replacements.append(
                    {
                        "mode": "fuzzy",
                        "from": token,
                        "to": corrected,
                        "score": round(score, 3),
                    }
                )
            else:
                corrected_tokens.append(token)

        normalized = "".join(corrected_tokens)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return TextNormalizationResult(
            original_text=text,
            normalized_text=normalized,
            replacements=replacements,
        )
