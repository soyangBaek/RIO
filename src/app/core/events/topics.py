"""Canonical topic registry for RIO events."""

VOICE_ACTIVITY_STARTED = "voice.activity.started"
VOICE_ACTIVITY_ENDED = "voice.activity.ended"
VOICE_INTENT_DETECTED = "voice.intent.detected"
VOICE_INTENT_UNKNOWN = "voice.intent.unknown"

VISION_FACE_DETECTED = "vision.face.detected"
VISION_FACE_LOST = "vision.face.lost"
VISION_FACE_MOVED = "vision.face.moved"
VISION_GESTURE_DETECTED = "vision.gesture.detected"

TOUCH_TAP_DETECTED = "touch.tap.detected"
TOUCH_STROKE_DETECTED = "touch.stroke.detected"

TIMER_EXPIRED = "timer.expired"

TASK_STARTED = "task.started"
TASK_SUCCEEDED = "task.succeeded"
TASK_FAILED = "task.failed"

SMARTHOME_REQUEST_SENT = "smarthome.request.sent"
SMARTHOME_RESULT = "smarthome.result"
WEATHER_RESULT = "weather.result"

CONTEXT_STATE_CHANGED = "context.state.changed"
ACTIVITY_STATE_CHANGED = "activity.state.changed"
ONESHOT_TRIGGERED = "oneshot.triggered"
SCENE_DERIVED = "scene.derived"

SYSTEM_WORKER_HEARTBEAT = "system.worker.heartbeat"
SYSTEM_DEGRADED_ENTERED = "system.degraded.entered"
SYSTEM_ALERT_TIMEOUT = "system.alert.timeout"


ALL_TOPICS = {
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
    SYSTEM_ALERT_TIMEOUT,
}

