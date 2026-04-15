from __future__ import annotations

from src.app.domains.smart_home.payloads import SmartHomeCommand, build_smart_home_command


def map_intent_to_home_request(intent: str) -> SmartHomeCommand:
    return build_smart_home_command(intent)
