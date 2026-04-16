"""T-026: Intent parser – alias 처리 + canonical intent 매핑.

triggers.yaml의 alias 리스트로 자연어 텍스트를 정규화된 intent로 변환.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 기본 intent alias (triggers.yaml 로딩 전 fallback)
DEFAULT_ALIASES: Dict[str, List[str]] = {
    "dance.start": ["춤 춰", "댄스", "dance", "춤 시작"],
    "camera.capture": ["사진 찍어", "사진", "찍어", "capture", "photo", "셀카"],
    "ui.game_mode.enter": ["게임", "게임 하자", "game"],
    "timer.create": ["타이머", "timer", "알람"],
    "weather.current": ["날씨", "weather", "오늘 날씨"],
    "smarthome.aircon.on": ["에어컨 켜", "에어컨", "aircon"],
    "smarthome.light.on": ["불 켜", "조명", "light on"],
    "smarthome.robot_cleaner.start": ["청소기", "로봇 청소기", "청소"],
    "smarthome.tv.on": ["TV 켜", "텔레비전", "tv on"],
    "smarthome.music.play": ["음악 틀어", "노래", "music"],
    "system.cancel": ["취소", "cancel", "그만"],
    "system.ack": ["알겠어", "확인", "ok", "ack"],
}


class IntentParser:
    """텍스트 → canonical intent 변환."""

    def __init__(self, triggers_config: Optional[Dict[str, Any]] = None) -> None:
        self._aliases: Dict[str, List[str]] = {}
        self._load_aliases(triggers_config)

    def _load_aliases(self, config: Optional[Dict[str, Any]]) -> None:
        """triggers config 에서 alias 로딩."""
        if config and "intents" in config:
            for intent, aliases in config["intents"].items():
                if isinstance(aliases, list) and aliases:
                    self._aliases[intent] = [a.lower() for a in aliases]
                else:
                    # alias가 비어있으면 기본값 사용
                    if intent in DEFAULT_ALIASES:
                        self._aliases[intent] = DEFAULT_ALIASES[intent]
        else:
            self._aliases = {k: [a.lower() for a in v] for k, v in DEFAULT_ALIASES.items()}

    def parse(self, text: str, confidence: float = 1.0) -> Tuple[Optional[str], float]:
        """텍스트에서 intent 추출.

        Returns: (intent_or_None, adjusted_confidence)
        """
        if not text:
            return None, 0.0

        text_lower = text.lower().strip()

        # 정확 매칭 먼저
        for intent, aliases in self._aliases.items():
            for alias in aliases:
                if alias in text_lower:
                    return intent, confidence

        return None, confidence * 0.5

    def get_all_intents(self) -> List[str]:
        return list(self._aliases.keys())
