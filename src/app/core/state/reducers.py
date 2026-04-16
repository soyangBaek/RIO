"""Reducer pipeline — the authoritative per-event processing order.

Architecture §4 specifies the sequence:

    extended_state update → Context FSM → Activity FSM → oneshot dispatch →
    scene derivation → adapter effects

This module owns steps 2–5 and the side-effect stamping required between
them (``away_started_at`` on Context transitions, ``activity_started_at`` on
Activity transitions, ``active_executing_kind`` when entering/leaving
``Executing``). Derived events (``context.state.changed``,
``activity.state.changed``, ``oneshot.triggered``, ``scene.derived``) are
buffered during the locked mutation and published **after** the lock is
released so downstream handlers cannot reenter the store mid-reduce.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..bus.router import Router
from ..events import topics
from ..events.models import Event
from . import activity_fsm, context_fsm, extended_state, oneshot, scene_selector
from .activity_fsm import ActivityThresholds
from .context_fsm import ContextThresholds
from .models import (
    Activity,
    ActivityKind,
    Context,
    Oneshot,
    Scene,
)
from .oneshot import OneshotPolicy
from .store import StateStore


def _activity_label(a: Activity) -> str:
    if a.kind is ActivityKind.EXECUTING:
        return f"executing({a.executing.value})"  # type: ignore[union-attr]
    return a.kind.value


@dataclass
class ReducerConfig:
    context: ContextThresholds = field(default_factory=ContextThresholds)
    activity: ActivityThresholds = field(default_factory=ActivityThresholds)
    oneshot_policy: OneshotPolicy = field(default_factory=OneshotPolicy)


class Reducer:
    def __init__(
        self,
        store: StateStore,
        router: Router,
        config: Optional[ReducerConfig] = None,
    ) -> None:
        self._store = store
        self._router = router
        self._cfg = config if config is not None else ReducerConfig()
        self._last_scene: Optional[Scene] = None

    def reduce(self, event: Event) -> Scene:
        """Process one event and return the resulting :class:`Scene`."""
        now = event.timestamp
        to_emit: List[Event] = []

        with self._store.mutate() as state:
            # Step 1: extended state update (from the raw input event)
            extended_state.apply_event(state.extended, event)

            # Step 2: Context FSM
            old_context = state.context
            new_context = context_fsm.transition(
                old_context, event, state.extended, now, self._cfg.context
            )
            state.context = new_context
            if new_context is not old_context:
                if new_context is Context.AWAY:
                    extended_state.mark_away_start(state.extended, now)
                # Leaving Away: keep away_started_at briefly so the oneshot
                # dispatcher can still evaluate ``just_reappeared``. We clear
                # it a few lines below, *after* the oneshot check runs.
                to_emit.append(
                    Event(
                        topic=topics.CONTEXT_STATE_CHANGED,
                        payload={
                            "from": old_context.value,
                            "to": new_context.value,
                        },
                        timestamp=now,
                        trace_id=event.trace_id,
                        source="main",
                    )
                )

            # Step 3: Activity FSM
            old_activity = state.activity
            new_activity = activity_fsm.transition(
                old_activity, event, state.extended, now, self._cfg.activity
            )
            if new_activity != old_activity:
                state.activity = new_activity
                state.extended.activity_started_at = now
                if new_activity.kind is ActivityKind.EXECUTING:
                    extended_state.set_executing_kind(
                        state.extended, new_activity.executing
                    )
                else:
                    extended_state.set_executing_kind(state.extended, None)
                payload = {
                    "from": _activity_label(old_activity),
                    "to": _activity_label(new_activity),
                }
                if new_activity.executing is not None:
                    payload["kind"] = new_activity.executing.value
                to_emit.append(
                    Event(
                        topic=topics.ACTIVITY_STATE_CHANGED,
                        payload=payload,
                        timestamp=now,
                        trace_id=event.trace_id,
                        source="main",
                    )
                )

            # Step 4: oneshot — expire first so triggers see a clean slot
            state.active_oneshot = oneshot.expire_if_done(
                state.active_oneshot, now
            )
            prior_oneshot = state.active_oneshot
            candidate = oneshot.trigger_for_event(
                event,
                old_context,
                new_context,
                state.extended,
                now,
                self._cfg.oneshot_policy,
            )
            if candidate is not None:
                resolved = oneshot.dispatch(
                    prior_oneshot, candidate, now, self._cfg.oneshot_policy
                )
                if resolved is not prior_oneshot:
                    state.active_oneshot = resolved
                    to_emit.append(
                        Event(
                            topic=topics.ONESHOT_TRIGGERED,
                            payload={
                                "name": resolved.name.value,
                                "duration_ms": resolved.duration_ms,
                                "priority": resolved.priority,
                            },
                            timestamp=now,
                            trace_id=event.trace_id,
                            source="main",
                        )
                    )

            # Clear ``away_started_at`` only once welcome's window has been
            # evaluated. A transition Away/Sleepy -> Idle that does not meet
            # the welcome_min_away_ms gate still clears here, which is
            # desirable (no lingering stamp for future transitions).
            if (
                old_context in (Context.AWAY, Context.SLEEPY)
                and new_context is Context.IDLE
            ):
                state.extended.away_started_at = None

            # Step 5: scene derivation
            new_scene = scene_selector.derive(
                state.context, state.activity, state.active_oneshot
            )
            if new_scene != self._last_scene:
                self._last_scene = new_scene
                to_emit.append(
                    Event(
                        topic=topics.SCENE_DERIVED,
                        payload={
                            "mood": new_scene.mood.value,
                            "ui": new_scene.ui.value,
                        },
                        timestamp=now,
                        trace_id=event.trace_id,
                        source="main",
                    )
                )

        for ev in to_emit:
            self._router.publish(ev)
        return new_scene
