from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import yaml


INTENT_TO_DEVICE_ACTION = {
    "smarthome.aircon.on": ("aircon", "on"),
    "smarthome.aircon.off": ("aircon", "off"),
    "smarthome.light.on": ("light", "on"),
    "smarthome.light.off": ("light", "off"),
    "smarthome.robot_cleaner.start": ("robot_cleaner", "start"),
    "smarthome.robot_cleaner.stop": ("robot_cleaner", "stop"),
    "smarthome.tv.on": ("tv", "on"),
    "smarthome.tv.off": ("tv", "off"),
    "smarthome.music.play": ("music", "play"),
    "smarthome.music.stop": ("music", "stop"),
}


@dataclass(slots=True)
class SmartHomeCommand:
    intent: str
    device_key: str
    device_id: str
    action: str
    content: str
    display_name: str


@lru_cache(maxsize=4)
def load_device_config(path: str = "configs/devices.yaml") -> dict[str, object]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return {}


def build_smart_home_command(
    intent: str,
    *,
    devices_path: str = "configs/devices.yaml",
) -> SmartHomeCommand:
    mapping = INTENT_TO_DEVICE_ACTION.get(intent)
    if mapping is None:
        raise KeyError(f"Unsupported smart-home intent: {intent}")
    device_key, action = mapping
    config = load_device_config(devices_path)
    devices = config.get("devices", {})
    device_cfg = devices.get(device_key, {}) if isinstance(devices, dict) else {}
    device_id = str(device_cfg.get("id") or device_key)
    display_name = str(device_cfg.get("name") or device_key)
    content = str(device_cfg.get("template") or "{device_id}:{action}").format(
        device_id=device_id,
        action=action,
    )
    return SmartHomeCommand(
        intent=intent,
        device_key=device_key,
        device_id=device_id,
        action=action,
        content=content,
        display_name=display_name,
    )
