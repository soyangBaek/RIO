from __future__ import annotations

from src.app.core.events.models import Event
from src.app.core.events import topics


def build_hud_message(event: Event) -> str | None:
    if event.topic == topics.VOICE_ACTIVITY_STARTED:
        return "Listening"
    if event.topic == topics.VOICE_INTENT_UNKNOWN:
        return "Didn't catch that"
    if event.topic == topics.TOUCH_TAP_DETECTED:
        return "Tap!"
    if event.topic == topics.TOUCH_STROKE_DETECTED:
        return "Yay!"
    if event.topic == topics.VISION_GESTURE_DETECTED:
        gesture = event.payload.get("gesture")
        if gesture == "wave":
            return "Hello!"
        if gesture == "finger_gun":
            return "Bang!"
        if gesture == "peekaboo":
            return "Peekaboo!"
        if gesture == "head_left":
            return "Head game: Left"
        if gesture == "head_right":
            return "Head game: Right"
    if event.topic == topics.TIMER_EXPIRED:
        return "Timer done"
    if event.topic == topics.SMARTHOME_RESULT:
        return "Control OK" if event.payload.get("ok") else "Control failed"
    if event.topic == topics.WEATHER_RESULT:
        return event.payload.get("speech_text") or ("Weather OK" if event.payload.get("ok") else "Weather failed")
    if event.topic == topics.TASK_SUCCEEDED and event.payload.get("kind") == "game":
        return "Game mode ready"
    if event.topic == topics.TASK_SUCCEEDED and event.payload.get("kind") == "photo":
        return "Photo saved"
    if event.topic == topics.TASK_SUCCEEDED and event.payload.get("kind") == "timer_setup":
        delay = event.payload.get("delay_seconds")
        if isinstance(delay, (int, float)) and delay > 0:
            total = int(delay)
            if total >= 60 and total % 60 == 0:
                return f"Timer set: {total // 60} min"
            return f"Timer set: {total}s"
        return "Timer set"
    return None
