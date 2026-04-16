"""Effect planner — turn state-change events into SFX / TTS commands.

The renderer (T-019) already subscribes to ``scene.derived``,
``vision.face.moved`` and the HUD-source events directly. This planner fills
the remaining gap: playing the right sound and speaking the right line as
states change.

Mapping lives in :data:`ONESHOT_SFX`, :data:`TASK_SFX`, etc., so tuning is a
config change rather than a code change. The planner is intentionally thin —
it does not hold state; it just reacts.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from ...adapters.speaker import SFXPlayer
from ...adapters.speaker.tts import TTS, NullTTS
from ...core.events import topics
from ...core.events.models import Event
from ...core.state.models import OneshotName

_log = logging.getLogger(__name__)


# oneshot name → SFX slot name (None = visual-only).
ONESHOT_SFX: Dict[str, Optional[str]] = {
    OneshotName.STARTLED.value: "startle",
    OneshotName.CONFUSED.value: "fail",
    OneshotName.HAPPY.value: "satisfaction",
    OneshotName.WELCOME.value: None,  # chime is optional; leave visual-only
}

# task.kind → SFX on success / failure.
TASK_SUCCESS_SFX: Dict[str, str] = {
    "photo": "shutter",
    "smarthome": "success",
    "weather": "success",
    "timer_setup": "success",
}
TASK_FAILURE_SFX: Dict[str, str] = {
    "weather": "fail",
    "smarthome": "fail",
    "timer_setup": "fail",
}


class EffectPlanner:
    def __init__(
        self,
        sfx: SFXPlayer,
        tts: Optional[TTS] = None,
    ) -> None:
        self._sfx = sfx
        self._tts = tts if tts is not None else NullTTS()

    # -- router entry --------------------------------------------------------
    def on_event(self, event: Event) -> None:
        topic = event.topic
        if topic == topics.ONESHOT_TRIGGERED:
            self._on_oneshot(event)
            return
        if topic == topics.TASK_SUCCEEDED:
            self._on_task_succeeded(event)
            return
        if topic == topics.TASK_FAILED:
            self._on_task_failed(event)
            return
        if topic == topics.TIMER_EXPIRED:
            self._on_timer_expired(event)
            return
        if topic == topics.WEATHER_RESULT:
            self._on_weather_result(event)
            return
        if topic == topics.SMARTHOME_RESULT:
            self._on_smarthome_result(event)
            return

    # -- individual handlers ------------------------------------------------
    def _on_oneshot(self, event: Event) -> None:
        name = event.payload.get("name")
        slot = ONESHOT_SFX.get(str(name)) if name else None
        if slot:
            self._sfx.play(slot)

    def _on_task_succeeded(self, event: Event) -> None:
        kind = event.payload.get("kind", "")
        slot = TASK_SUCCESS_SFX.get(str(kind))
        if slot:
            self._sfx.play(slot)

    def _on_task_failed(self, event: Event) -> None:
        kind = event.payload.get("kind", "")
        slot = TASK_FAILURE_SFX.get(str(kind))
        if slot:
            self._sfx.play(slot)

    def _on_timer_expired(self, event: Event) -> None:
        self._sfx.play("success")  # alarm uses the success tone for MVP
        label = event.payload.get("label")
        msg = f"타이머 {label} 완료" if label else "타이머 완료"
        self._tts.speak(msg, priority=5)

    def _on_weather_result(self, event: Event) -> None:
        if not event.payload.get("ok"):
            return
        data = event.payload.get("data") or {}
        t = data.get("temperature_c")
        c = data.get("condition")
        parts = []
        if c:
            parts.append(str(c))
        if t is not None:
            parts.append(f"{t}도")
        if parts:
            self._tts.speak("현재 날씨는 " + ", ".join(parts) + " 입니다.")

    def _on_smarthome_result(self, event: Event) -> None:
        if event.payload.get("ok"):
            self._sfx.play("success")
        else:
            self._sfx.play("fail")
