#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def inject_local_venv_site_packages() -> None:
    venv_lib = REPO_ROOT / ".venv" / "lib"
    if not venv_lib.exists():
        return
    for site_packages in venv_lib.glob("python*/site-packages"):
        if str(site_packages) not in sys.path:
            sys.path.insert(0, str(site_packages))


inject_local_venv_site_packages()

from src.app.adapters.vision.camera_stream import CameraStream
from src.app.adapters.vision.face_detector import FaceDetector
from src.app.adapters.vision.face_tracker import FaceTracker
from src.app.adapters.vision.gesture_detector import GestureDetector
from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.core.state.context_fsm import ContextThresholds
from src.app.core.state.reducers import ReducerPipeline
from src.app.main import RioOrchestrator
from src.app.core.state.scene_selector import select_scene


RESET = "\033[0m"
CLEAR = "\033[2J\033[H"
MOOD_STYLES = {
    "inactive": "\033[40;37m",
    "calm": "\033[44;37m",
    "attentive": "\033[46;30m",
    "sleepy": "\033[45;37m",
    "alert": "\033[41;37m",
    "startled": "\033[43;30m",
    "confused": "\033[100;37m",
    "welcome": "\033[42;30m",
    "happy": "\033[102;30m",
}


def load_yaml(path: str) -> dict[str, object]:
    file_path = REPO_ROOT / path
    if not file_path.exists():
        return {}
    with file_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def print_state(rio: RioOrchestrator, last_gesture: str | None) -> None:
    snapshot = rio.store.snapshot()
    frame = rio.renderer.history[-1] if rio.renderer.history else None
    if frame is None:
        return

    mood = frame.face.mood
    style = MOOD_STYLES.get(mood, "")
    print(CLEAR, end="")
    print("RIO Live Vision State Test")
    print("Press Ctrl+C to exit.")
    print()
    for _ in range(6):
        print(f"{style}{' ' * 64}{RESET}")
    print()
    print(f"context     : {snapshot.context_state.value}")
    print(f"activity    : {snapshot.activity_state.value}")
    print(f"mood        : {frame.face.mood}")
    print(f"ui          : {frame.ui}")
    print(f"face_present: {snapshot.extended.face_present}")
    print(f"gesture     : {last_gesture}")
    print(f"overlay     : {frame.overlay.name}")
    print(f"hud         : {frame.hud.message}")
    print(f"tts         : {rio.tts.history[-1] if rio.tts.history else '-'}")
    print()
    print("Test tips:")
    print("  Show face only: Away -> Idle")
    print("  Show open_palm while face visible: Idle -> Engaged")
    print("  v_sign maps to camera.capture, triggers photo sequence")


def ensure_initial_frame(rio: RioOrchestrator) -> None:
    if rio.renderer.history:
        return
    snapshot = rio.store.snapshot()
    scene = select_scene(
        snapshot.context_state,
        snapshot.activity_state,
        snapshot.extended,
        snapshot.active_oneshot,
    )
    rio.renderer.render(scene)


def process_frame(
    rio: RioOrchestrator,
    stream: CameraStream,
    face_detector: FaceDetector,
    face_tracker: FaceTracker,
    gesture_detector: GestureDetector,
    *,
    had_face: bool,
) -> tuple[bool, str | None, bool]:
    now = datetime.now(timezone.utc)
    frame = stream.read()
    face_event = face_detector.detect(frame, now=now)
    last_gesture: str | None = None
    state_changed = False

    if face_event is not None:
        had_face = True
        before = rio.store.snapshot()
        rio.process_event(face_event)
        after = rio.store.snapshot()
        state_changed = state_changed or before.context_state != after.context_state or before.activity_state != after.activity_state
        center = tuple(face_event.payload.get("center", (0.5, 0.5)))
        for moved in face_tracker.update(center, now=now):
            rio.process_event(moved)
    elif had_face:
        had_face = False
        before = rio.store.snapshot()
        rio.process_event(Event.create(topics.VISION_FACE_LOST, "live_vision", timestamp=now))
        after = rio.store.snapshot()
        state_changed = state_changed or before.context_state != after.context_state or before.activity_state != after.activity_state

    for gesture_event in gesture_detector.detect(frame, now=now):
        last_gesture = str(gesture_event.payload.get("gesture"))
        before = rio.store.snapshot()
        rio.process_event(gesture_event)
        after = rio.store.snapshot()
        state_changed = state_changed or before.context_state != after.context_state or before.activity_state != after.activity_state

    return had_face, last_gesture, state_changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify face/hand recognition state changes via Webcam + MediaPipe")
    parser.add_argument("--fps", type=float, default=8.0, help="loop refresh rate")
    parser.add_argument("--away-timeout-ms", type=int, default=3000, help="time until Away transition after face lost")
    parser.add_argument("--engaged-idle-ms", type=int, default=1500, help="Engaged -> Idle timeout without interaction")
    parser.add_argument("--sleepy-ms", type=int, default=15000, help="Idle -> Sleepy timeout")
    args = parser.parse_args()

    robot_cfg = load_yaml("configs/robot.yaml")
    thresholds = load_yaml("configs/thresholds.yaml")
    webcam = robot_cfg.get("webcam", {}) if isinstance(robot_cfg, dict) else {}
    vision = thresholds.get("vision", {}) if isinstance(thresholds, dict) else {}
    presence = thresholds.get("presence", {}) if isinstance(thresholds, dict) else {}

    try:
        stream = CameraStream(
            device_index=int(webcam.get("device_index", 0)),
            width=int(webcam.get("width", 640)),
            height=int(webcam.get("height", 480)),
            fps=int(webcam.get("fps", 15)),
            use_camera=True,
        )
        face_detector = FaceDetector(confidence_min=float(vision.get("face_confidence_min", 0.6)))
        face_tracker = FaceTracker(sample_hz=float(presence.get("face_moved_sample_hz", 10)))
        gesture_detector = GestureDetector(confidence_min=float(vision.get("gesture_confidence_min", 0.75)))
        rio = RioOrchestrator(audio_worker=None, vision_worker=None)
        rio.reducer = ReducerPipeline(
            rio.store,
            thresholds=ContextThresholds(
                away_timeout_ms=args.away_timeout_ms,
                idle_to_sleepy_timeout_ms=args.sleepy_ms,
                engaged_to_idle_timeout_ms=args.engaged_idle_ms,
                welcome_min_away_ms=1000,
                face_lost_timeout_ms=800,
            ),
        )
    except Exception as exc:
        print(f"Initialization failed: {exc}")
        print("Make sure `.venv/bin/python -m pip install mediapipe` is done first.")
        return 1

    had_face = False
    last_gesture: str | None = None
    last_rendered_signature: tuple[str, str, str | None, str | None] | None = None
    frame_interval = 1.0 / max(args.fps, 1.0)
    ensure_initial_frame(rio)
    print_state(rio, last_gesture)

    try:
        while True:
            had_face, detected_gesture, _ = process_frame(
                rio,
                stream,
                face_detector,
                face_tracker,
                gesture_detector,
                had_face=had_face,
            )
            if detected_gesture is not None:
                last_gesture = detected_gesture

            if rio.renderer.history:
                frame = rio.renderer.history[-1]
                snapshot = rio.store.snapshot()
                signature = (
                    snapshot.context_state.value,
                    snapshot.activity_state.value,
                    frame.face.mood,
                    last_gesture,
                )
                if signature != last_rendered_signature:
                    print_state(rio, last_gesture)
                    last_rendered_signature = signature

            time.sleep(frame_interval)
    except KeyboardInterrupt:
        print("\nExiting.")
        return 0
    finally:
        stream.close()


if __name__ == "__main__":
    raise SystemExit(main())
