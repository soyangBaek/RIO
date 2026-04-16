"""T-039: Intent normalizer – STT 텍스트를 canonical intent 로 변환.

audio_worker 내부에서 사용. speech/intent_parser 래퍼.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from src.app.domains.speech.intent_parser import IntentParser

logger = logging.getLogger(__name__)


class IntentNormalizer:
    """STT 결과 → canonical intent 변환."""

    def __init__(self, triggers_config: Optional[Dict[str, Any]] = None, min_confidence: float = 0.5) -> None:
        self._parser = IntentParser(triggers_config)
        self._min_confidence = min_confidence

    def normalize(self, text: str, stt_confidence: float) -> Tuple[Optional[str], float]:
        """텍스트 + STT confidence → (intent, adjusted_confidence).

        stt_confidence < min_confidence → (None, confidence) 즉 voice.intent.unknown.
        """
        if stt_confidence < self._min_confidence:
            return None, stt_confidence

        intent, intent_conf = self._parser.parse(text, stt_confidence)
        return intent, intent_conf

    @property
    def intent_parser(self) -> IntentParser:
        return self._parser
