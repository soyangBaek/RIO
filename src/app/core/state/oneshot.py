from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping

import yaml

from src.app.core.config import resolve_repo_path
from src.app.core.state.models import Oneshot, OneshotName


DEFAULT_ONESHOT_SETTINGS: dict[str, dict[str, int]] = {
    "startled": {"priority": 30, "duration_ms": 600},
    "confused": {"priority": 25, "duration_ms": 800},
    "welcome": {"priority": 20, "duration_ms": 1500},
    "happy": {"priority": 20, "duration_ms": 1000},
}


def load_oneshot_settings(path: str | Path = "configs/scenes.yaml") -> dict[str, dict[str, int]]:
    cfg_path = resolve_repo_path(path)
    if not cfg_path.exists():
        return deepcopy(DEFAULT_ONESHOT_SETTINGS)
    with cfg_path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    configured = loaded.get("oneshots", {})
    merged = deepcopy(DEFAULT_ONESHOT_SETTINGS)
    for name, values in configured.items():
        if name in merged:
            merged[name].update(values or {})
    return merged


@dataclass(slots=True)
class OneshotDecision:
    active: Oneshot | None
    changed: bool


class OneshotDispatcher:
    def __init__(self, settings: Mapping[str, Mapping[str, int]] | None = None) -> None:
        self.settings = {
            key: dict(value)
            for key, value in (settings or DEFAULT_ONESHOT_SETTINGS).items()
        }

    def expire(self, active: Oneshot | None, now: datetime) -> Oneshot | None:
        if active and active.is_expired(now):
            return None
        return active

    def build(self, name: OneshotName | str, now: datetime) -> Oneshot:
        key = str(name)
        config = self.settings.get(key, DEFAULT_ONESHOT_SETTINGS[key])
        return Oneshot(
            name=OneshotName(key),
            priority=int(config["priority"]),
            duration_ms=int(config["duration_ms"]),
            started_at=now,
        )

    def trigger(
        self,
        active: Oneshot | None,
        name: OneshotName | str,
        now: datetime,
    ) -> OneshotDecision:
        candidate = self.build(name, now)
        current = self.expire(active, now)
        if current is None:
            return OneshotDecision(active=candidate, changed=True)
        if candidate.priority > current.priority:
            return OneshotDecision(active=candidate, changed=True)
        if candidate.priority < current.priority:
            return OneshotDecision(active=current, changed=False)
        if current.elapsed_ratio(now) >= 0.8:
            return OneshotDecision(active=candidate, changed=True)
        return OneshotDecision(active=current, changed=False)
