"""T-010: Oneshot dispatcher – 순간 반응 이벤트 발화/중첩 정책.

state-machine.md §5 기준.
- Priority preempt
- Same priority coalesce (80% 교체 규칙)
- Lower priority drop
- Queue 금지
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from src.app.core.state.models import OneshotName
from src.app.core.state.store import ActiveOneshot, Store

# 기본값 – scenes.yaml / thresholds.yaml 에서 override 가능
DEFAULT_ONESHOTS: Dict[str, Dict[str, Any]] = {
    "startled": {"priority": 30, "duration_ms": 600},
    "confused": {"priority": 25, "duration_ms": 800},
    "welcome": {"priority": 20, "duration_ms": 1500},
    "happy": {"priority": 20, "duration_ms": 1000},
}


def try_trigger_oneshot(
    store: Store,
    name: OneshotName,
    config: Dict[str, Any],
) -> bool:
    """oneshot 발화를 시도. 성공하면 True, 중첩 정책에 의해 무시되면 False."""
    now = time.time()
    oneshot_cfg = _get_oneshot_config(name, config)
    new_priority = oneshot_cfg["priority"]
    new_duration = oneshot_cfg["duration_ms"]

    current = store.active_oneshot

    # 만료된 oneshot 정리
    if current is not None and current.is_expired:
        store.active_oneshot = None
        current = None

    if current is None:
        # 활성 oneshot 없음 → 즉시 발화
        store.active_oneshot = ActiveOneshot(
            name=name,
            priority=new_priority,
            started_at=now,
            duration_ms=new_duration,
        )
        return True

    # ── 중첩 정책 ────────────────────────────────────────────
    # 1. Priority preempt: 새 priority > 현재 → 즉시 교체
    if new_priority > current.priority:
        store.active_oneshot = ActiveOneshot(
            name=name,
            priority=new_priority,
            started_at=now,
            duration_ms=new_duration,
        )
        return True

    # 2. Same priority coalesce: 무시, 단 80% 이상 경과 시 교체
    if new_priority == current.priority:
        if current.elapsed_ratio >= 0.8:
            store.active_oneshot = ActiveOneshot(
                name=name,
                priority=new_priority,
                started_at=now,
                duration_ms=new_duration,
            )
            return True
        # 같은 priority → 무시 (깜빡임 방지)
        return False

    # 3. Lower priority drop
    return False


def expire_oneshot_if_done(store: Store) -> Optional[OneshotName]:
    """만료된 oneshot 을 정리. 정리된 이름을 반환, 없으면 None."""
    if store.active_oneshot and store.active_oneshot.is_expired:
        name = store.active_oneshot.name
        store.active_oneshot = None
        return name
    return None


def _get_oneshot_config(name: OneshotName, config: Dict[str, Any]) -> Dict[str, Any]:
    """scenes config 에서 oneshot 설정을 가져오거나 기본값 반환."""
    scenes_cfg = config.get("oneshots", {})
    cfg = scenes_cfg.get(name.value, {})
    defaults = DEFAULT_ONESHOTS.get(name.value, {"priority": 20, "duration_ms": 1000})
    return {
        "priority": cfg.get("priority", defaults["priority"]),
        "duration_ms": cfg.get("duration_ms", defaults["duration_ms"]),
    }
