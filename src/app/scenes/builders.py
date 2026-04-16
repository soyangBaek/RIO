"""T-056: Scene builder – 상태 조합에서 씬 이름 결정.

(Mood, UI, oneshot) → scene_name.
"""
from __future__ import annotations

from typing import Optional

from src.app.core.state.models import (
    ActivityState,
    ContextState,
    ExecutingKind,
    Mood,
    OneshotName,
    UILayout,
)
from src.app.core.state.store import ActiveOneshot


class SceneBuilder:
    """상태 → 씬 이름 매핑."""

    def resolve_scene(
        self,
        mood: Mood,
        ui: UILayout,
        active_oneshot: Optional[ActiveOneshot] = None,
        executing_kind: Optional[ExecutingKind] = None,
    ) -> str:
        """현재 상태 조합에서 씬 이름 결정."""

        # Oneshot 우선
        if active_oneshot and not active_oneshot.is_expired:
            return self._oneshot_scene(active_oneshot.name)

        # Activity 기반
        if ui == UILayout.ALERT_UI:
            return "alert_timer"
        if ui == UILayout.CAMERA_UI:
            return "take_photo_countdown"
        if ui == UILayout.GAME_UI:
            return "dance_mode" if executing_kind == ExecutingKind.DANCE else "game_mode"
        if ui == UILayout.LISTENING_UI:
            return "listening"
        if ui == UILayout.SLEEP_UI:
            return "sleep_mode_loop"

        # Mood 기반
        if mood == Mood.ATTENTIVE:
            return "attentive_face"
        if mood == Mood.CALM:
            return "calm_face"
        if mood == Mood.SLEEPY and ui == UILayout.NORMAL_FACE_DIM:
            return "sleepy_dim"

        return "calm_face"

    @staticmethod
    def _oneshot_scene(name: OneshotName) -> str:
        return {
            OneshotName.STARTLED: "startled_then_track",
            OneshotName.CONFUSED: "confused_reaction",
            OneshotName.WELCOME: "welcome_back",
            OneshotName.HAPPY: "petting_reaction",
        }.get(name, "calm_face")
