"""T-034: SmartHome payloads – intent → home-client 요청 변환.

architecture.md §5.2 계약: PUT /device/control, body: {"content": "<command>"}.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class SmartHomePayload:
    """home-client 요청 payload."""
    content: str
    intent: str
    device: Optional[str] = None

    def to_body(self) -> Dict[str, Any]:
        """HTTP body 생성."""
        body: Dict[str, Any] = {"content": self.content}
        if self.device:
            body["device"] = self.device
        return body


# intent → command 매핑
INTENT_COMMANDS: Dict[str, str] = {
    "smarthome.aircon.on": "에어컨 켜줘",
    "smarthome.light.on": "불 켜줘",
    "smarthome.robot_cleaner.start": "로봇 청소기 시작",
    "smarthome.tv.on": "TV 켜줘",
    "smarthome.music.play": "음악 틀어줘",
}


def build_payload(intent: str, text: str = "", device: Optional[str] = None) -> SmartHomePayload:
    """intent에서 SmartHomePayload 생성."""
    content = text if text else INTENT_COMMANDS.get(intent, intent)
    return SmartHomePayload(content=content, intent=intent, device=device)
