from __future__ import annotations

from src.app.core.events.models import Event
from src.app.core.events import topics


def build_hud_message(event: Event) -> str | None:
    if event.topic == topics.VOICE_ACTIVITY_STARTED:
        return "듣고 있어"
    if event.topic == topics.VOICE_INTENT_UNKNOWN:
        return "잘 못 들었어"
    if event.topic == topics.TOUCH_TAP_DETECTED:
        return "톡!"
    if event.topic == topics.TOUCH_STROKE_DETECTED:
        return "좋아!"
    if event.topic == topics.VISION_GESTURE_DETECTED:
        gesture = event.payload.get("gesture")
        if gesture == "wave":
            return "안녕!"
        if gesture == "finger_gun":
            return "빵야!"
        if gesture == "peekaboo":
            return "찾았다!"
        if gesture == "head_left":
            return "참참참: 왼쪽"
        if gesture == "head_right":
            return "참참참: 오른쪽"
    if event.topic == topics.TIMER_EXPIRED:
        return "타이머 완료"
    if event.topic == topics.SMARTHOME_RESULT:
        return "제어 성공" if event.payload.get("ok") else "제어 실패"
    if event.topic == topics.WEATHER_RESULT:
        return event.payload.get("speech_text") or ("날씨 조회 성공" if event.payload.get("ok") else "날씨 조회 실패")
    if event.topic == topics.TASK_SUCCEEDED and event.payload.get("kind") == "game":
        return "게임 모드 준비 완료"
    if event.topic == topics.TASK_SUCCEEDED and event.payload.get("kind") == "photo":
        return "사진 저장 완료"
    return None
