"""Topic registry for the RIO event bus.

Authoritative source: ``docs/architecture.md`` §6.3. Topics follow the rule
``<domain>.<object>.<verb-past>`` from §6.2 — imperative topics are forbidden;
commands travel as an ``intent`` field inside a ``voice.intent.detected``
payload. Producer and consumer code should import these constants rather than
spell topic strings inline so that all subscribers stay aligned with the
single registry in this module.

When a new topic is required, add it to architecture.md §6.3 first, then
mirror the entry here and extend :data:`ALL_TOPICS`.

Canonical voice intent IDs (``camera.capture``, ``timer.create``,
``smarthome.aircon.on``, ``system.cancel``, …) are **not** topics — they are
string values carried in the ``intent`` field of a ``voice.intent.detected``
payload and live in :mod:`configs.triggers` / :mod:`app.domains.speech`.
"""
from __future__ import annotations

from typing import FrozenSet

# -- voice (source: audio_worker) -------------------------------------------
VOICE_ACTIVITY_STARTED = "voice.activity.started"
VOICE_ACTIVITY_ENDED = "voice.activity.ended"
VOICE_INTENT_DETECTED = "voice.intent.detected"        # payload: intent, text, confidence
VOICE_INTENT_UNKNOWN = "voice.intent.unknown"          # payload: text, confidence

# -- vision (source: vision_worker) -----------------------------------------
VISION_FACE_DETECTED = "vision.face.detected"          # payload: bbox, center, confidence
VISION_FACE_LOST = "vision.face.lost"                  # payload: last_seen_at
VISION_FACE_MOVED = "vision.face.moved"                # payload: center, delta
VISION_GESTURE_DETECTED = "vision.gesture.detected"    # payload: gesture, confidence

# -- touch (source: main/touch) ---------------------------------------------
TOUCH_TAP_DETECTED = "touch.tap.detected"              # payload: x, y
TOUCH_STROKE_DETECTED = "touch.stroke.detected"        # payload: path, duration

# -- timer/scheduler (source: main/scheduler) -------------------------------
TIMER_EXPIRED = "timer.expired"                        # payload: timer_id, label

# -- task execution (source: main/executor) ---------------------------------
TASK_STARTED = "task.started"                          # payload: task_id, kind
TASK_SUCCEEDED = "task.succeeded"                      # payload: task_id, kind, result
TASK_FAILED = "task.failed"                            # payload: task_id, kind, error

# -- smarthome (source: main/home_client) -----------------------------------
SMARTHOME_REQUEST_SENT = "smarthome.request.sent"      # payload: intent, content
SMARTHOME_RESULT = "smarthome.result"                  # payload: ok, status, error?

# -- weather (source: main/weather) -----------------------------------------
WEATHER_RESULT = "weather.result"                      # payload: ok, data?, error?

# -- behavior-derived state (source: main/behavior) -------------------------
CONTEXT_STATE_CHANGED = "context.state.changed"        # payload: from, to
ACTIVITY_STATE_CHANGED = "activity.state.changed"      # payload: from, to, kind?
ONESHOT_TRIGGERED = "oneshot.triggered"                # payload: name, duration_ms, priority
SCENE_DERIVED = "scene.derived"                        # payload: mood, ui

# -- system / safety --------------------------------------------------------
SYSTEM_WORKER_HEARTBEAT = "system.worker.heartbeat"    # payload: worker, status
SYSTEM_DEGRADED_ENTERED = "system.degraded.entered"    # payload: reason, lost_capability


ALL_TOPICS: FrozenSet[str] = frozenset({
    VOICE_ACTIVITY_STARTED,
    VOICE_ACTIVITY_ENDED,
    VOICE_INTENT_DETECTED,
    VOICE_INTENT_UNKNOWN,
    VISION_FACE_DETECTED,
    VISION_FACE_LOST,
    VISION_FACE_MOVED,
    VISION_GESTURE_DETECTED,
    TOUCH_TAP_DETECTED,
    TOUCH_STROKE_DETECTED,
    TIMER_EXPIRED,
    TASK_STARTED,
    TASK_SUCCEEDED,
    TASK_FAILED,
    SMARTHOME_REQUEST_SENT,
    SMARTHOME_RESULT,
    WEATHER_RESULT,
    CONTEXT_STATE_CHANGED,
    ACTIVITY_STATE_CHANGED,
    ONESHOT_TRIGGERED,
    SCENE_DERIVED,
    SYSTEM_WORKER_HEARTBEAT,
    SYSTEM_DEGRADED_ENTERED,
})

ALLOWED_DOMAINS: FrozenSet[str] = frozenset({
    "voice", "vision", "touch", "timer", "task", "scene",
    "context", "activity", "oneshot", "smarthome", "weather", "system",
})


def is_known(topic: str) -> bool:
    """Return True if ``topic`` is registered in :data:`ALL_TOPICS`."""
    return topic in ALL_TOPICS


def domain_of(topic: str) -> str:
    """Return the leading domain segment of ``topic`` (e.g. ``"vision"``).

    The event router uses this to group subscriptions without hard-coding the
    list of topics. Raises :class:`ValueError` if the topic has no dot, which
    would violate the naming rule in architecture.md §6.2.
    """
    if "." not in topic:
        raise ValueError(f"topic must follow <domain>.<object>.<verb> form: {topic!r}")
    return topic.split(".", 1)[0]
