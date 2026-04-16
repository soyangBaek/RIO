"""T-048: 스마트홈 장치 매퍼.

intent → device ID 매핑. devices.yaml 기반.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class DeviceMapper:
    """intent/장치명 → device ID 매핑."""

    def __init__(self, devices_config: Optional[Dict[str, Any]] = None) -> None:
        self._devices: Dict[str, Dict[str, Any]] = {}
        if devices_config and "devices" in devices_config:
            self._devices = devices_config["devices"]

    def resolve_device(self, intent: str) -> Optional[str]:
        """intent 에서 device name/id 추출.

        예: smarthome.aircon.on → 'aircon'
        """
        parts = intent.split(".")
        if len(parts) >= 2 and parts[0] == "smarthome":
            device_key = parts[1]  # e.g. 'aircon', 'light'
            if device_key in self._devices:
                return self._devices[device_key].get("id", device_key)
            return device_key
        return None

    def get_device_info(self, device_key: str) -> Dict[str, Any]:
        """장치 정보 조회."""
        return self._devices.get(device_key, {})

    @property
    def registered_devices(self) -> list:
        return list(self._devices.keys())
