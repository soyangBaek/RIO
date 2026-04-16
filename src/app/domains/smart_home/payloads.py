"""Smart-home request body builder.

The home-client exposes a single endpoint
(``PUT /device/control {"content": "..."}``) that accepts a natural-
language command. This module maps a canonical intent id (see
``docs/prd.md``) to the appropriate content string, optionally substituting
a device alias from ``configs/devices.yaml`` (e.g. ``aircon`` → ``거실 에어컨``).
"""
from __future__ import annotations

from typing import Dict, Optional


# Each entry is ``(device_key, action_phrase)``. ``device_key`` is looked up
# in the ``devices`` map (from ``devices.yaml``) with a Korean default.
_INTENT_ACTIONS: Dict[str, tuple] = {
    "smarthome.aircon.on": ("aircon", "{device} 켜줘"),
    "smarthome.aircon.off": ("aircon", "{device} 꺼줘"),
    "smarthome.light.on": ("light", "{device} 켜줘"),
    "smarthome.light.off": ("light", "{device} 꺼줘"),
    "smarthome.robot_cleaner.start": ("robot_cleaner", "{device} 시작해줘"),
    "smarthome.tv.on": ("tv", "{device} 켜줘"),
    "smarthome.music.play": ("music", "{device} 틀어줘"),
}

# Default Korean labels when devices.yaml does not override.
_DEFAULT_DEVICE_LABELS: Dict[str, str] = {
    "aircon": "에어컨",
    "light": "불",
    "robot_cleaner": "청소기",
    "tv": "TV",
    "music": "음악",
}


def is_smarthome_intent(intent_id: str) -> bool:
    return intent_id in _INTENT_ACTIONS


def build_content(
    intent_id: str,
    devices: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Return the natural-language command or ``None`` if intent unsupported."""
    entry = _INTENT_ACTIONS.get(intent_id)
    if entry is None:
        return None
    device_key, template = entry
    label = (devices or {}).get(device_key) or _DEFAULT_DEVICE_LABELS[device_key]
    return template.format(device=label)


def build_request(
    intent_id: str,
    devices: Optional[Dict[str, str]] = None,
) -> Optional[dict]:
    content = build_content(intent_id, devices)
    if content is None:
        return None
    return {"content": content}
