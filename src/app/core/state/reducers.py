"""T-012: Reducers – extended state update → FSM transition → oneshot trigger 조합.

메인 루프에서 이벤트 하나를 받아 상태 갱신 전체 파이프라인을 실행.
project-layout.md §5.state 기준.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.app.core.events.models import Event
from src.app.core.events.topics import Topics
from src.app.core.state.activity_fsm import activity_transition
from src.app.core.state.context_fsm import context_transition
from src.app.core.state.extended_state import (
    just_reappeared,
    update_extended_state,
)
from src.app.core.state.models import (
    ActivityState,
    ContextState,
    ExecutingKind,
    Mood,
    OneshotName,
    UILayout,
)
from src.app.core.state.oneshot import expire_oneshot_if_done, try_trigger_oneshot
from src.app.core.state.scene_selector import derive_scene
from src.app.core.state.store import Store

logger = logging.getLogger(__name__)


@dataclass
class ReducerResult:
    """한 이벤트 처리 후 결과."""

    context_changed: bool = False
    prev_context: Optional[ContextState] = None
    new_context: Optional[ContextState] = None

    activity_changed: bool = False
    prev_activity: Optional[ActivityState] = None
    new_activity: Optional[ActivityState] = None
    new_executing_kind: Optional[ExecutingKind] = None

    oneshot_triggered: Optional[OneshotName] = None
    oneshot_expired: Optional[OneshotName] = None

    mood: Mood = Mood.CALM
    ui: UILayout = UILayout.NORMAL_FACE

    # 생성된 출력 이벤트들
    output_events: List[Event] = None  # type: ignore

    def __post_init__(self):
        if self.output_events is None:
            self.output_events = []


def reduce(store: Store, event: Event, config: Dict[str, Any]) -> ReducerResult:
    """메인 루프의 한 턴: 이벤트 → 상태 갱신 → 결과."""
    result = ReducerResult()
    now = event.timestamp or time.time()

    # ── 1) Extended state update ─────────────────────────────
    update_extended_state(store, event, config)

    # ── 2) Oneshot 만료 체크 ─────────────────────────────────
    expired = expire_oneshot_if_done(store)
    if expired:
        result.oneshot_expired = expired

    # ── 3) Context FSM transition ────────────────────────────
    prev_context = store.context_state
    ctx_trans = context_transition(store, event, config)
    if ctx_trans:
        from_ctx, to_ctx = ctx_trans
        store.context_state = to_ctx
        result.context_changed = True
        result.prev_context = from_ctx
        result.new_context = to_ctx

        # away_started_at 갱신
        if to_ctx == ContextState.AWAY:
            store.away_started_at = now
        elif from_ctx == ContextState.AWAY:
            # Away 에서 벗어남
            pass

        result.output_events.append(
            Event(
                topic=Topics.CONTEXT_STATE_CHANGED,
                source="main/behavior",
                payload={"from": from_ctx.value, "to": to_ctx.value},
                timestamp=now,
            )
        )

    # ── 4) Activity FSM transition ───────────────────────────
    prev_activity = store.activity_state
    act_trans = activity_transition(store, event, config)
    if act_trans:
        from_act, to_act, kind = act_trans
        store.activity_state = to_act
        result.activity_changed = True
        result.prev_activity = from_act
        result.new_activity = to_act
        result.new_executing_kind = kind

        # executing kind 갱신
        if to_act == ActivityState.EXECUTING and kind:
            store.active_executing_kind = kind
        elif to_act != ActivityState.EXECUTING:
            store.active_executing_kind = None

        # Executing → Idle: deferred_intent 소비
        if from_act == ActivityState.EXECUTING and to_act == ActivityState.IDLE:
            if store.deferred_intent:
                deferred = store.deferred_intent
                store.deferred_intent = None
                result.output_events.append(
                    Event(
                        topic=Topics.VOICE_INTENT_DETECTED,
                        source="main/deferred",
                        payload=deferred,
                        timestamp=now,
                    )
                )

        result.output_events.append(
            Event(
                topic=Topics.ACTIVITY_STATE_CHANGED,
                source="main/behavior",
                payload={
                    "from": from_act.value,
                    "to": to_act.value,
                    "kind": kind.value if kind else None,
                },
                timestamp=now,
            )
        )

    # ── 5) Oneshot triggers ──────────────────────────────────
    oneshot_to_trigger = _determine_oneshot(store, event, prev_context, config)
    if oneshot_to_trigger:
        if try_trigger_oneshot(store, oneshot_to_trigger, config):
            result.oneshot_triggered = oneshot_to_trigger
            os_cfg = config.get("oneshots", {}).get(oneshot_to_trigger.value, {})
            from src.app.core.state.oneshot import DEFAULT_ONESHOTS
            defaults = DEFAULT_ONESHOTS.get(oneshot_to_trigger.value, {})
            result.output_events.append(
                Event(
                    topic=Topics.ONESHOT_TRIGGERED,
                    source="main/behavior",
                    payload={
                        "name": oneshot_to_trigger.value,
                        "duration_ms": os_cfg.get("duration_ms", defaults.get("duration_ms", 1000)),
                        "priority": os_cfg.get("priority", defaults.get("priority", 20)),
                    },
                    timestamp=now,
                )
            )

    # ── 6) Scene derivation ──────────────────────────────────
    mood, ui = derive_scene(
        store.context_state,
        store.activity_state,
        store.active_oneshot,
        store.active_executing_kind,
    )
    result.mood = mood
    result.ui = ui
    result.output_events.append(
        Event(
            topic=Topics.SCENE_DERIVED,
            source="main/behavior",
            payload={"mood": mood.value, "ui": ui.value},
            timestamp=now,
        )
    )

    return result


def _determine_oneshot(
    store: Store,
    event: Event,
    prev_context: ContextState,
    config: Dict[str, Any],
) -> Optional[OneshotName]:
    """이벤트 기반 oneshot 트리거 결정."""
    topic = event.topic

    # startled: 얼굴 없이 큰 소리 (voice_started + no face)
    if topic == Topics.VOICE_ACTIVITY_STARTED and not store.face_present:
        return OneshotName.STARTLED

    # confused: intent 해석 실패
    if topic == Topics.VOICE_INTENT_UNKNOWN:
        return OneshotName.CONFUSED

    # welcome: just_reappeared
    if topic == Topics.VISION_FACE_DETECTED:
        if just_reappeared(store, prev_context.value, config):
            return OneshotName.WELCOME

    # happy: 쓰다듬기, 성공 피드백
    if topic == Topics.TOUCH_STROKE_DETECTED:
        return OneshotName.HAPPY
    if topic == Topics.TASK_SUCCEEDED:
        return OneshotName.HAPPY

    # happy: smarthome 성공
    if topic == Topics.SMARTHOME_RESULT:
        if event.payload.get("ok"):
            return OneshotName.HAPPY
        else:
            return OneshotName.CONFUSED

    return None
