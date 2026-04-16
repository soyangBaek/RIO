"""T-002: 이벤트 topic 상수 레지스트리.

architecture.md §6.3 topic 레지스트리와 정합.
새 topic 추가 시 architecture.md 표를 먼저 수정한 뒤 여기에 반영.
"""


class Topics:
    """전체 이벤트 topic 상수. <domain>.<object>.<verb-past> 규칙."""

    # ── voice (source: audio_worker) ─────────────────────────
    VOICE_ACTIVITY_STARTED = "voice.activity.started"
    VOICE_ACTIVITY_ENDED = "voice.activity.ended"
    VOICE_INTENT_DETECTED = "voice.intent.detected"
    VOICE_INTENT_UNKNOWN = "voice.intent.unknown"

    # ── vision (source: vision_worker) ───────────────────────
    VISION_FACE_DETECTED = "vision.face.detected"
    VISION_FACE_LOST = "vision.face.lost"
    VISION_FACE_MOVED = "vision.face.moved"
    VISION_GESTURE_DETECTED = "vision.gesture.detected"

    # ── touch (source: main/touch) ───────────────────────────
    TOUCH_TAP_DETECTED = "touch.tap.detected"
    TOUCH_STROKE_DETECTED = "touch.stroke.detected"

    # ── timer (source: main/scheduler) ───────────────────────
    TIMER_EXPIRED = "timer.expired"

    # ── task lifecycle (source: main/executor) ───────────────
    TASK_STARTED = "task.started"
    TASK_SUCCEEDED = "task.succeeded"
    TASK_FAILED = "task.failed"

    # ── smarthome (source: main/home_client) ─────────────────
    SMARTHOME_REQUEST_SENT = "smarthome.request.sent"
    SMARTHOME_RESULT = "smarthome.result"

    # ── weather (source: main/weather) ───────────────────────
    WEATHER_RESULT = "weather.result"

    # ── state-machine outputs (source: main/behavior) ────────
    CONTEXT_STATE_CHANGED = "context.state.changed"
    ACTIVITY_STATE_CHANGED = "activity.state.changed"
    ONESHOT_TRIGGERED = "oneshot.triggered"
    SCENE_DERIVED = "scene.derived"

    # ── system (source: workers / main/safety) ───────────────
    SYSTEM_WORKER_HEARTBEAT = "system.worker.heartbeat"
    SYSTEM_DEGRADED_ENTERED = "system.degraded.entered"

    # ── user evidence 판정 helper ────────────────────────────
    USER_EVIDENCE_TOPICS = frozenset(
        {
            VISION_FACE_DETECTED,
            VOICE_ACTIVITY_STARTED,
            TOUCH_TAP_DETECTED,
            TOUCH_STROKE_DETECTED,
        }
    )

    INTERACTION_TOPICS = frozenset(
        {
            VOICE_ACTIVITY_STARTED,
            VOICE_INTENT_DETECTED,
            TOUCH_TAP_DETECTED,
            TOUCH_STROKE_DETECTED,
            VISION_GESTURE_DETECTED,
        }
    )
