from __future__ import annotations

from dataclasses import dataclass

from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.core.state.models import ExtendedState


USER_EVIDENCE_TOPICS = {
    topics.VISION_FACE_DETECTED,
    topics.VOICE_ACTIVITY_STARTED,
    topics.TOUCH_TAP_DETECTED,
    topics.TOUCH_STROKE_DETECTED,
}

INTERACTION_TOPICS = {
    topics.VOICE_ACTIVITY_STARTED,
    topics.VOICE_INTENT_DETECTED,
    topics.TOUCH_TAP_DETECTED,
    topics.TOUCH_STROKE_DETECTED,
    topics.VISION_GESTURE_DETECTED,
}


@dataclass(slots=True)
class PresenceSignals:
    face_present: bool
    voice_detected: bool
    touch_detected: bool
    gesture_detected: bool
    user_evidence_detected: bool
    interaction_detected: bool
    confirmed_user_and_interacting: bool


def aggregate_presence_signals(event: Event, extended: ExtendedState) -> PresenceSignals:
    """Summarize user-presence facts from the current event plus extended state."""

    voice_detected = event.topic in {
        topics.VOICE_ACTIVITY_STARTED,
        topics.VOICE_INTENT_DETECTED,
        topics.VOICE_INTENT_UNKNOWN,
    }
    touch_detected = event.topic in {
        topics.TOUCH_TAP_DETECTED,
        topics.TOUCH_STROKE_DETECTED,
    }
    gesture_detected = event.topic == topics.VISION_GESTURE_DETECTED
    user_evidence_detected = event.topic in USER_EVIDENCE_TOPICS
    interaction_detected = event.topic in INTERACTION_TOPICS

    confirmed_user_and_interacting = bool(
        extended.face_present and interaction_detected
    )
    return PresenceSignals(
        face_present=extended.face_present,
        voice_detected=voice_detected,
        touch_detected=touch_detected,
        gesture_detected=gesture_detected,
        user_evidence_detected=user_evidence_detected,
        interaction_detected=interaction_detected,
        confirmed_user_and_interacting=confirmed_user_and_interacting,
    )
