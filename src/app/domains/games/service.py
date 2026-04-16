"""T-054: 게임 서비스.

게임 모드 진입/퇴장. MVP에서는 GameUI 전환만 구현.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict

logger = logging.getLogger(__name__)


class GameService:
    """게임 도메인 서비스."""

    def __init__(self) -> None:
        self._active_game: str | None = None

    def handle(self, payload: Dict[str, Any], done_callback: Callable) -> None:
        """executor_registry 핸들러.

        MVP: 게임 모드 UI 전환 → 일정 시간 후 종료.
        """
        t = threading.Thread(
            target=self._run_game, args=(payload, done_callback), daemon=True
        )
        t.start()

    def _run_game(self, payload: Dict[str, Any], done_callback: Callable) -> None:
        try:
            game_type = payload.get("game_type", "default")
            self._active_game = game_type
            logger.info("Game started: %s", game_type)

            # MVP: 10초 후 자동 종료 (실제 게임 로직은 Phase 2 확장)
            time.sleep(10)

            self._active_game = None
            done_callback(True, result={"game_type": game_type})

        except Exception as e:
            self._active_game = None
            logger.exception("Game error")
            done_callback(False, error=str(e))

    @property
    def is_playing(self) -> bool:
        return self._active_game is not None
