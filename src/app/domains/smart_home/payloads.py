from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Mapping, Any

import yaml

from src.app.core.config import resolve_repo_path


INTENT_TO_DEVICE_ACTION = {
    "smarthome.aircon.on": ("aircon", "on"),
    "smarthome.aircon.off": ("aircon", "off"),
    "smarthome.aircon.set_temperature": ("aircon", "set_temperature"),
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
    action_label: str
    params: dict[str, object] = field(default_factory=dict)


@lru_cache(maxsize=4)
def load_device_config(path: str = "configs/devices.yaml") -> dict[str, object]:
    try:
        with resolve_repo_path(path).open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return {}


def build_smart_home_command(
    intent: str,
    *,
    payload: Mapping[str, Any] | None = None,
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
    params = dict(payload or {})
    action_cfg_raw = device_cfg.get("actions", {}).get(action, {}) if isinstance(device_cfg.get("actions"), dict) else {}
    action_cfg = action_cfg_raw if isinstance(action_cfg_raw, dict) else {"template": action_cfg_raw}
    template = str(action_cfg.get("template") or device_cfg.get("template") or "{device_id}:{action}")
    action_label = str(action_cfg.get("label") or action.replace("_", " "))
    format_values = {"device_id": device_id, "action": action, **params}
    try:
        content = template.format(**format_values)
    except KeyError as exc:
        raise ValueError(f"Missing smart-home payload field for template: {exc.args[0]}") from exc
    return SmartHomeCommand(
        intent=intent,
        device_key=device_key,
        device_id=device_id,
        action=action,
        content=content,
        display_name=display_name,
        action_label=action_label,
        params=params,
    )
