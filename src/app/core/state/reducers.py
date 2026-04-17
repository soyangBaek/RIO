from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from src.app.core.events.models import Event
from src.app.core.events import topics
from src.app.core.state.activity_fsm import transition_activity
from src.app.core.state.context_fsm import ContextThresholds, load_thresholds, transition_context
from src.app.core.state.extended_state import apply_extended_state
from src.app.core.state.models import (
    ActivityState,
    ContextState,
    OneshotName,
    ReductionResult,
    RuntimeState,
)
from src.app.core.state.oneshot import OneshotDispatcher
from src.app.core.state.scene_selector import select_scene
from src.app.core.state.store import RuntimeStore


class ReducerPipeline:
    """Extended-state update -> FSM transition -> oneshot -> scene selection."""

    def __init__(
        self,
        store: RuntimeStore,
        *,
        thresholds: ContextThresholds | None = None,
        oneshots: OneshotDispatcher | None = None,
    ) -> None:
        self.store = store
        self.thresholds = thresholds or load_thresholds()
        self.oneshots = oneshots or OneshotDispatcher()

    def process(self, event: Event) -> ReductionResult:
        previous = self.store.snapshot()
        current = deepcopy(previous)
        now = event.timestamp

        current.extended = apply_extended_state(current.extended, event, now=now)
        current.active_oneshot = self.oneshots.expire(current.active_oneshot, now)

        next_activity, next_kind = transition_activity(
            current.activity_state,
            event,
            current.extended.active_executing_kind,
            now=now,
        )
        current.activity_state = next_activity
        current.extended.active_executing_kind = next_kind

        next_context = transition_context(
            current.context_state,
            event,
            current.extended,
            self.thresholds,
            now=now,
        )
        previous_context = current.context_state
        current.context_state = next_context

        if current.context_state != previous_context:
            current.extended.previous_context_state = previous_context
            if current.context_state in {ContextState.AWAY, ContextState.SLEEPY}:
                current.extended.away_started_at = now

        emitted: list[Event] = []
        if previous.context_state != current.context_state:
            emitted.append(
                Event.create(
                    topics.CONTEXT_STATE_CHANGED,
                    "reducers",
                    payload={"from": previous.context_state.value, "to": current.context_state.value},
                    timestamp=now,
                    trace_id=event.trace_id,
                )
            )
        if (
            previous.activity_state != current.activity_state
            or previous.extended.active_executing_kind != current.extended.active_executing_kind
        ):
            payload = {
                "from": previous.activity_state.value,
                "to": current.activity_state.value,
            }
            if current.extended.active_executing_kind is not None:
                payload["kind"] = current.extended.active_executing_kind.value
            emitted.append(
                Event.create(
                    topics.ACTIVITY_STATE_CHANGED,
                    "reducers",
                    payload=payload,
                    timestamp=now,
                    trace_id=event.trace_id,
                )
            )

        candidate_oneshot: OneshotName | None = None
        if (
            event.topic == topics.VOICE_ACTIVITY_STARTED
            and not current.extended.face_present
            and event.source != "audio.terminal_input"
        ):
            candidate_oneshot = OneshotName.STARTLED
        elif event.topic == topics.VOICE_INTENT_UNKNOWN:
            candidate_oneshot = OneshotName.CONFUSED
        elif event.topic == topics.TOUCH_TAP_DETECTED and previous.context_state == ContextState.SLEEPY:
            candidate_oneshot = OneshotName.STARTLED
        elif event.topic == topics.TOUCH_STROKE_DETECTED:
            candidate_oneshot = OneshotName.HAPPY
        elif event.topic == topics.VISION_GESTURE_DETECTED:
            gesture = event.payload.get("gesture")
            if gesture in {"wave", "peekaboo"}:
                candidate_oneshot = OneshotName.WELCOME
            elif gesture == "finger_gun":
                candidate_oneshot = OneshotName.STARTLED
        elif event.topic == topics.SMARTHOME_RESULT:
            candidate_oneshot = (
                OneshotName.HAPPY if event.payload.get("ok") else OneshotName.CONFUSED
            )
        elif event.topic == topics.WEATHER_RESULT and not event.payload.get("ok", True):
            candidate_oneshot = OneshotName.CONFUSED
        elif event.topic == topics.TASK_FAILED:
            candidate_oneshot = OneshotName.CONFUSED
        elif (
            previous.context_state in {ContextState.AWAY, ContextState.SLEEPY}
            and current.context_state == ContextState.IDLE
            and current.extended.away_started_at is not None
            and (now - current.extended.away_started_at).total_seconds() * 1000.0
            >= self.thresholds.welcome_min_away_ms
        ):
            candidate_oneshot = OneshotName.WELCOME

        triggered_oneshot = None
        if candidate_oneshot is not None:
            decision = self.oneshots.trigger(current.active_oneshot, candidate_oneshot, now)
            current.active_oneshot = decision.active
            if decision.changed and decision.active is not None:
                triggered_oneshot = decision.active
                emitted.append(
                    Event.create(
                        topics.ONESHOT_TRIGGERED,
                        "reducers",
                        payload={
                            "name": decision.active.name.value,
                            "priority": decision.active.priority,
                            "duration_ms": decision.active.duration_ms,
                        },
                        timestamp=now,
                        trace_id=event.trace_id,
                    )
                )

        scene = select_scene(
            current.context_state,
            current.activity_state,
            current.extended,
            current.active_oneshot,
        )
        previous_scene = select_scene(
            previous.context_state,
            previous.activity_state,
            previous.extended,
            previous.active_oneshot,
        )
        if previous_scene != scene:
            emitted.append(
                Event.create(
                    topics.SCENE_DERIVED,
                    "reducers",
                    payload={"mood": scene.mood.value, "ui": scene.ui.value},
                    timestamp=now,
                    trace_id=event.trace_id,
                )
            )

        self.store.replace(current)
        return ReductionResult(
            previous=previous,
            current=current,
            scene=scene,
            emitted_events=emitted,
            triggered_oneshot=triggered_oneshot,
        )
