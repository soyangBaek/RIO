"""T-035: SmartHome service – intent → home_client 요청 → 결과 피드백.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Dict, Optional

from src.app.domains.smart_home.payloads import build_payload

logger = logging.getLogger(__name__)


class SmartHomeService:
    """스마트홈 도메인 서비스."""

    def __init__(self, home_client: Any = None) -> None:
        self._client = home_client

    def handle(self, payload: Dict[str, Any], done_callback: Callable) -> None:
        """executor_registry 핸들러.

        비동기로 home_client 호출.
        """
        t = threading.Thread(
            target=self._execute, args=(payload, done_callback), daemon=True
        )
        t.start()

    def _execute(self, payload: Dict[str, Any], done_callback: Callable) -> None:
        try:
            intent = payload.get("intent", "")
            text = payload.get("text", "")

            sh_payload = build_payload(intent, text)

            if self._client:
                result = self._client.send_command(sh_payload.to_body())
                if result.get("ok"):
                    done_callback(True, result=result)
                else:
                    done_callback(False, error=result.get("error", "Unknown error"))
            else:
                # dummy – no client
                logger.info("SmartHome (dummy): %s → %s", intent, sh_payload.content)
                done_callback(True, result={"ok": True, "intent": intent})

        except Exception as e:
            logger.exception("SmartHome service error")
            done_callback(False, error=str(e))
