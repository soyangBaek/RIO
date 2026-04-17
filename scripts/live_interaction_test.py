#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import select
import sys
import time
from functools import lru_cache
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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

import cv2
import numpy as np

from src.app.adapters.audio.intent_normalizer import IntentNormalizer
from src.app.adapters.audio.terminal_input import TerminalVoiceInput
from src.app.adapters.vision.camera_stream import CameraStream
from src.app.adapters.vision.face_detector import FaceDetector
from src.app.adapters.vision.face_tracker import FaceTracker
from src.app.adapters.vision.gesture_detector import GestureDetector
from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.core.state.context_fsm import ContextThresholds
from src.app.core.state.models import ActionKind, ActivityState, ContextState
from src.app.core.state.reducers import ReducerPipeline
from src.app.core.state.scene_selector import select_scene
from src.app.domains.behavior.executor_registry import ExecutionResult
from src.app.domains.smart_home.payloads import build_smart_home_command
from src.app.main import RioOrchestrator


INTENT_LABELS = {
    "camera.capture": "사진 촬영",
    "weather.current": "날씨 조회",
    "smarthome.aircon.on": "에어컨 켜기",
    "smarthome.aircon.off": "에어컨 끄기",
    "smarthome.aircon.set_temperature": "에어컨 온도 설정",
    "smarthome.light.on": "조명 켜기",
    "smarthome.light.off": "조명 끄기",
    "smarthome.robot_cleaner.start": "로봇청소기 시작",
    "smarthome.tv.on": "TV 켜기",
    "smarthome.music.play": "음악 재생",
    "ui.game_mode.enter": "게임 모드 전환",
    "dance.start": "댄스 모드 실행",
    "timer.create": "타이머 생성",
    "system.cancel": "현재 동작 취소",
    "system.ack": "알림 확인",
}

ACTION_LABELS = {
    ActionKind.PHOTO: "사진 촬영",
    ActionKind.WEATHER: "날씨 조회",
    ActionKind.SMARTHOME: "스마트홈 제어",
    ActionKind.TIMER_SETUP: "타이머 등록",
    ActionKind.GAME: "게임 모드 전환",
    ActionKind.DANCE: "댄스 모드 실행",
}

RECENT_ACTION_HOLD_MS = 1500


def load_yaml(path: str) -> dict[str, object]:
    file_path = REPO_ROOT / path
    if not file_path.exists():
        return {}
    with file_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def configure_mock_services(rio: RioOrchestrator) -> None:
    def fake_weather_handler(request) -> ExecutionResult:
        return ExecutionResult(
            events=[
                Event.create(
                    topics.TASK_STARTED,
                    "live.weather",
                    payload={"task_id": "weather-live", "kind": ActionKind.WEATHER.value},
                    trace_id=request.trace_id,
                ),
                Event.create(
                    topics.WEATHER_RESULT,
                    "live.weather",
                    payload={"ok": True, "condition": "맑음", "temperature_c": 22.0},
                    trace_id=request.trace_id,
                ),
                Event.create(
                    topics.TASK_SUCCEEDED,
                    "live.weather",
                    payload={"task_id": "weather-live", "kind": ActionKind.WEATHER.value},
                    trace_id=request.trace_id,
                ),
            ]
        )

    def fake_smarthome_handler(request) -> ExecutionResult:
        spoken = str(request.payload.get("text") or request.intent)
        try:
            command = build_smart_home_command(request.intent, payload=request.payload)
            content = command.content
        except Exception:
            content = spoken
        return ExecutionResult(
            events=[
                Event.create(
                    topics.TASK_STARTED,
                    "live.smarthome",
                    payload={"task_id": "smarthome-live", "kind": ActionKind.SMARTHOME.value},
                    trace_id=request.trace_id,
                ),
                Event.create(
                    topics.SMARTHOME_REQUEST_SENT,
                    "live.smarthome",
                    payload={
                        "task_id": "smarthome-live",
                        "intent": request.intent,
                        "content": content,
                        "request_url": "mock://home-client/device/control",
                        "transport": "mock",
                    },
                    trace_id=request.trace_id,
                ),
                Event.create(
                    topics.SMARTHOME_RESULT,
                    "live.smarthome",
                    payload={
                        "ok": True,
                        "message": f"'{spoken}' 명령을 처리했어.",
                        "request_url": "mock://home-client/device/control",
                        "response": {
                            "ok": True,
                            "request_url": "mock://home-client/device/control",
                            "request_method": "PUT",
                            "request_content": content,
                            "mock": True,
                        },
                    },
                    trace_id=request.trace_id,
                ),
                Event.create(
                    topics.TASK_SUCCEEDED,
                    "live.smarthome",
                    payload={"task_id": "smarthome-live", "kind": ActionKind.SMARTHOME.value},
                    trace_id=request.trace_id,
                ),
            ]
        )

    rio.registry.register(ActionKind.WEATHER, fake_weather_handler)
    rio.registry.register(ActionKind.SMARTHOME, fake_smarthome_handler)


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


def trim_text(text: str | None, *, limit: int = 44) -> str:
    if not text:
        return "-"
    value = " ".join(str(text).split())
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3]}..."


def find_recent_event(rio: RioOrchestrator, *wanted_topics: str) -> Event | None:
    targets = set(wanted_topics)
    for event in reversed(rio.event_log):
        if event.topic in targets:
            return event
    return None


def is_recent_event(event: Event | None, *, within_ms: int = RECENT_ACTION_HOLD_MS) -> bool:
    if event is None:
        return False
    age_ms = max((datetime.now(timezone.utc) - event.timestamp).total_seconds() * 1000.0, 0.0)
    return age_ms <= within_ms


def describe_recent_intent(rio: RioOrchestrator) -> str:
    latest_unknown = find_recent_event(rio, topics.VOICE_INTENT_UNKNOWN)
    event = find_recent_event(rio, topics.VOICE_INTENT_DETECTED)
    if event is None:
        return "-"
    if latest_unknown is not None and latest_unknown.timestamp > event.timestamp:
        return "-"
    text = str(event.payload.get("text") or "").strip()
    intent = str(event.payload.get("intent") or "")
    if text:
        return trim_text(text)
    return INTENT_LABELS.get(intent, intent or "-")


def describe_current_action(rio: RioOrchestrator) -> str:
    snapshot = rio.store.snapshot()
    if snapshot.activity_state == ActivityState.ALERTING:
        timer_event = find_recent_event(rio, topics.TIMER_EXPIRED)
        label = timer_event.payload.get("label") if timer_event else None
        return f"타이머 알림 출력 중 ({label})" if label else "타이머 알림 출력 중"

    if snapshot.activity_state == ActivityState.EXECUTING:
        kind = snapshot.extended.active_executing_kind
        label = ACTION_LABELS.get(kind, "동작 실행")
        if kind == ActionKind.PHOTO:
            return "사진 촬영 시퀀스 실행 중"
        if kind == ActionKind.WEATHER:
            return "날씨를 조회하는 중"
        if kind == ActionKind.SMARTHOME:
            intent_text = describe_recent_intent(rio)
            if intent_text != "-":
                return f"스마트홈 명령 실행 중: {intent_text}"
            return "스마트홈 명령 실행 중"
        if kind == ActionKind.TIMER_SETUP:
            return "타이머를 등록하는 중"
        if kind == ActionKind.GAME:
            return "게임 모드로 전환하는 중"
        if kind == ActionKind.DANCE:
            return "댄스 모드를 실행하는 중"
        return f"{label} 실행 중"

    if snapshot.activity_state == ActivityState.LISTENING:
        if snapshot.extended.face_present:
            return "사용자의 명령을 듣는 중"
        return "사용자를 찾으며 명령을 듣는 중"

    latest_unknown = find_recent_event(rio, topics.VOICE_INTENT_UNKNOWN)
    recent_smarthome_result = find_recent_event(rio, topics.SMARTHOME_RESULT)
    recent_smarthome_request = find_recent_event(rio, topics.SMARTHOME_REQUEST_SENT)
    recent_weather = find_recent_event(rio, topics.WEATHER_RESULT)
    recent_task = find_recent_event(rio, topics.TASK_SUCCEEDED, topics.TASK_FAILED)
    latest_completed = max(
        [
            event
            for event in [
                latest_unknown,
                recent_smarthome_result,
                recent_smarthome_request,
                recent_weather,
                recent_task,
            ]
            if event is not None and is_recent_event(event)
        ],
        key=lambda event: event.timestamp,
        default=None,
    )
    if latest_completed is not None:
        if latest_completed.topic == topics.VOICE_INTENT_UNKNOWN:
            return "명령을 이해하지 못해 다시 기다리는 중"
        if latest_completed.topic == topics.SMARTHOME_RESULT:
            intent_text = describe_recent_intent(rio)
            status = "완료" if latest_completed.payload.get("ok") else "실패"
            if intent_text != "-":
                return f"스마트홈 명령 {status}: {intent_text}"
            return f"스마트홈 명령 {status}"
        if latest_completed.topic == topics.SMARTHOME_REQUEST_SENT:
            intent_text = describe_recent_intent(rio)
            if intent_text != "-":
                return f"스마트홈 명령 전송: {intent_text}"
            return "스마트홈 명령 전송 중"
        if latest_completed.topic == topics.WEATHER_RESULT:
            return "날씨 조회 완료" if latest_completed.payload.get("ok", True) else "날씨 조회 실패"
        if latest_completed.topic in {topics.TASK_SUCCEEDED, topics.TASK_FAILED}:
            kind = str(latest_completed.payload.get("kind") or "")
            if kind == ActionKind.SMARTHOME.value:
                intent_text = describe_recent_intent(rio)
                status = "완료" if latest_completed.topic == topics.TASK_SUCCEEDED else "실패"
                if intent_text != "-":
                    return f"스마트홈 명령 {status}: {intent_text}"
                return f"스마트홈 명령 {status}"
            if kind == ActionKind.WEATHER.value:
                return "날씨 조회 완료" if latest_completed.topic == topics.TASK_SUCCEEDED else "날씨 조회 실패"
            if kind == ActionKind.PHOTO.value:
                return "사진 촬영 완료" if latest_completed.topic == topics.TASK_SUCCEEDED else "사진 촬영 실패"
            if kind == ActionKind.TIMER_SETUP.value:
                return "타이머 등록 완료" if latest_completed.topic == topics.TASK_SUCCEEDED else "타이머 등록 실패"
            if kind == ActionKind.GAME.value:
                return "게임 모드 전환 완료" if latest_completed.topic == topics.TASK_SUCCEEDED else "게임 모드 전환 실패"
            if kind == ActionKind.DANCE.value:
                return "댄스 모드 실행 완료" if latest_completed.topic == topics.TASK_SUCCEEDED else "댄스 모드 실행 실패"

    if snapshot.active_oneshot is not None:
        oneshot = snapshot.active_oneshot.name.value
        if oneshot == "startled":
            return "깜짝 반응을 보여주는 중"
        if oneshot == "welcome":
            return "사용자를 반겨주는 중"
        if oneshot == "happy":
            return "기뻐하는 반응을 보여주는 중"
        if oneshot == "confused":
            return "명령을 이해하지 못해 되묻는 중"

    if snapshot.context_state == ContextState.AWAY:
        return "사용자를 기다리며 대기 중"
    if snapshot.context_state == ContextState.SLEEPY:
        return "졸음 상태로 쉬는 중"
    if snapshot.context_state == ContextState.ENGAGED:
        return "사용자를 따라보며 상호작용 대기 중"
    return "기본 대기 상태"


def describe_last_result(rio: RioOrchestrator) -> str:
    weather = find_recent_event(rio, topics.WEATHER_RESULT)
    smarthome = find_recent_event(rio, topics.SMARTHOME_RESULT)
    unknown = find_recent_event(rio, topics.VOICE_INTENT_UNKNOWN)
    task_failed = find_recent_event(rio, topics.TASK_FAILED)
    task_succeeded = find_recent_event(rio, topics.TASK_SUCCEEDED)

    latest_domain = max(
        [event for event in [smarthome, weather, unknown] if event is not None],
        key=lambda event: event.timestamp,
        default=None,
    )
    if latest_domain is not None:
        if latest_domain.topic == topics.SMARTHOME_RESULT:
            prefix = "스마트홈 성공" if latest_domain.payload.get("ok") else "스마트홈 실패"
            message = trim_text(str(latest_domain.payload.get("message") or ""))
            return f"{prefix}: {message}" if message != "-" else prefix
        if latest_domain.topic == topics.WEATHER_RESULT:
            if latest_domain.payload.get("ok", True):
                condition = latest_domain.payload.get("condition", "알 수 없음")
                temperature = latest_domain.payload.get("temperature_c")
                if temperature is None:
                    return f"날씨 조회 완료: {condition}"
                return f"날씨 조회 완료: {condition}, {temperature}도"
            return trim_text(str(latest_domain.payload.get("message") or "날씨 조회 실패"))
        if latest_domain.topic == topics.VOICE_INTENT_UNKNOWN:
            return trim_text(str(latest_domain.payload.get("reason") or "명령 해석 실패"))

    latest = max([event for event in [task_failed, task_succeeded] if event is not None], key=lambda event: event.timestamp, default=None)
    if latest is None:
        return "-"

    if latest.topic == topics.WEATHER_RESULT:
        return "-"
    if latest.topic == topics.TASK_FAILED:
        kind = str(latest.payload.get("kind") or "작업")
        message = trim_text(str(latest.payload.get("message") or "실행 실패"))
        return f"{kind} 실패: {message}"
    if latest.topic == topics.TASK_SUCCEEDED:
        kind = str(latest.payload.get("kind") or "task")
        if kind == ActionKind.PHOTO.value:
            path = trim_text(str(latest.payload.get("photo_path") or "사진 저장 완료"))
            return f"사진 촬영 완료: {path}"
        if kind == ActionKind.GAME.value:
            return "게임 모드 전환 완료"
        if kind == ActionKind.DANCE.value:
            return "댄스 모드 실행 완료"
        if kind == ActionKind.TIMER_SETUP.value:
            label = trim_text(str(latest.payload.get("label") or "타이머"))
            delay_seconds = latest.payload.get("delay_seconds")
            if delay_seconds:
                return f"타이머 등록 완료: {label} ({delay_seconds}초)"
            return f"타이머 등록 완료: {label}"
        return f"{kind} 실행 완료"
    return "-"


def describe_http_snapshot(rio: RioOrchestrator, *, service_mode: str) -> dict[str, str]:
    last_voice_started = find_recent_event(rio, topics.VOICE_ACTIVITY_STARTED)
    request = find_recent_event(rio, topics.SMARTHOME_REQUEST_SENT)
    result = find_recent_event(rio, topics.SMARTHOME_RESULT)
    transport = service_mode
    sent = "no"
    target = "-"
    payload = "-"
    status = "-"

    if request is not None and (last_voice_started is None or request.timestamp >= last_voice_started.timestamp):
        transport = str(request.payload.get("transport") or service_mode)
        sent = "yes" if transport == "http" else "mock"
        target = trim_text(str(request.payload.get("request_url") or "-"), limit=52)
        payload = trim_text(str(request.payload.get("content") or "-"), limit=52)
        status = "pending"
        if result is not None and result.timestamp >= request.timestamp:
            status = "ok" if result.payload.get("ok") else "failed"

    return {
        "service_mode": service_mode,
        "http_transport": transport,
        "http_sent": sent,
        "http_status": status,
        "http_target": target,
        "http_payload": payload,
    }


def describe_runtime_snapshot(rio: RioOrchestrator, *, service_mode: str) -> dict[str, str]:
    snapshot = rio.store.snapshot()
    details = {
        "current_action": describe_current_action(rio),
        "last_intent": describe_recent_intent(rio),
        "last_result": describe_last_result(rio),
        "inflight": str(len(snapshot.extended.inflight_requests)),
    }
    details.update(describe_http_snapshot(rio, service_mode=service_mode))
    return details


def snapshot_signature(rio: RioOrchestrator, last_gesture: str | None, *, service_mode: str) -> tuple[str, ...]:
    snapshot = rio.store.snapshot()
    frame = rio.renderer.history[-1] if rio.renderer.history else None
    if frame is None:
        return ("empty",)
    oneshot = snapshot.active_oneshot.name.value if snapshot.active_oneshot else "-"
    last_tts = rio.tts.history[-1] if rio.tts.history else "-"
    last_sfx = rio.sfx.history[-1] if rio.sfx.history else "-"
    details = describe_runtime_snapshot(rio, service_mode=service_mode)
    return (
        snapshot.context_state.value,
        snapshot.activity_state.value,
        frame.face.mood,
        frame.ui,
        str(snapshot.extended.face_present),
        str(last_gesture or "-"),
        str(frame.overlay.name or "-"),
        str(frame.hud.message or "-"),
        oneshot,
        last_tts,
        last_sfx,
        details["current_action"],
        details["last_intent"],
        details["last_result"],
        details["inflight"],
        details["service_mode"],
        details["http_transport"],
        details["http_sent"],
        details["http_status"],
        details["http_target"],
        details["http_payload"],
    )


def print_snapshot(
    rio: RioOrchestrator,
    *,
    last_gesture: str | None,
    last_input: str | None,
    service_mode: str,
    reason: str,
) -> None:
    snapshot = rio.store.snapshot()
    frame = rio.renderer.history[-1] if rio.renderer.history else None
    if frame is None:
        return
    details = describe_runtime_snapshot(rio, service_mode=service_mode)
    recent_topics = [event.topic for event in rio.event_log[-6:]]
    print()
    print("=" * 72)
    print(f"[{reason}]")
    print(f"context     : {snapshot.context_state.value}")
    print(f"activity    : {snapshot.activity_state.value}")
    print(f"mood/ui     : {frame.face.mood} / {frame.ui}")
    print(f"doing       : {details['current_action']}")
    print(f"last_intent : {details['last_intent']}")
    print(f"last_result : {details['last_result']}")
    print(f"inflight    : {details['inflight']}")
    print(f"service_mode: {details['service_mode']}")
    print(f"http_mode   : {details['http_transport']}")
    print(f"http_sent   : {details['http_sent']}")
    print(f"http_status : {details['http_status']}")
    print(f"http_target : {details['http_target']}")
    print(f"http_payload: {details['http_payload']}")
    print(f"face_present: {snapshot.extended.face_present}")
    print(f"gesture     : {last_gesture or '-'}")
    print(f"oneshot     : {snapshot.active_oneshot.name.value if snapshot.active_oneshot else '-'}")
    print(f"overlay     : {frame.overlay.name or '-'}")
    print(f"hud         : {frame.hud.message or '-'}")
    print(f"tts         : {rio.tts.history[-1] if rio.tts.history else '-'}")
    print(f"sfx         : {rio.sfx.history[-1] if rio.sfx.history else '-'}")
    print(f"last_input  : {last_input or '-'}")
    print(f"recent      : {', '.join(recent_topics) if recent_topics else '-'}")
    print("=" * 72)


def print_help() -> None:
    print("RIO Live Interaction Test")
    print("Webcam reads face/hand gestures in real-time; voice is simulated via terminal strings.")
    print("Default preview is fullscreen robot face animation; use --debug to show webcam/sidebar.")
    print("Default uses mock services; use --real-services for actual HTTP requests.")
    print()
    print("Terminal input examples:")
    print("  사진 찍어줘")
    print("  날씨 알려줘")
    print("  불 켜줘")
    print("  게임 모드로 바꿔줘")
    print("  취소")
    print("  확인")
    print()
    print("Auxiliary commands:")
    print("  /tap           - touch tap event")
    print("  /stroke        - stroke event")
    print("  /gesture NAME  - simulate vision gesture (wave, finger_gun, v_sign, head_left, head_right, peekaboo)")
    print("  /face left|center|right|lost - simulate face position/loss")
    print("  /timer [label] - timer expiration event")
    print("  /status        - print current state")
    print("  /help          - help")
    print("  /quit          - quit")
    print()
    print("Webcam test tips:")
    print("  Show face only: Away -> Idle")
    print("  Show open_palm while face visible: Idle -> Engaged")
    print("  v_sign maps to camera.capture, triggers photo sequence")
    print("  Press q or ESC in preview window to exit")


def preview_center_to_pixels(frame: Any, center: tuple[float, float] | None) -> tuple[int, int] | None:
    if center is None or not hasattr(frame, "shape"):
        return None
    height, width = frame.shape[:2]
    x = int(max(0.0, min(1.0, center[0])) * width)
    y = int(max(0.0, min(1.0, center[1])) * height)
    return x, y


def rgb(red: int, green: int, blue: int) -> tuple[int, int, int]:
    return (blue, green, red)


ASSET_FACE_BG = rgb(201, 228, 195)
_FACE_ASSET_TRANSITION = {"current": None, "previous": None, "changed_at": 0.0}
_PREVIEW_WINDOW_MODE: str | None = None


def clamp_float(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def scale_color(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(int(clamp_float(channel * factor, 0, 255)) for channel in color)


def mix_color(
    left: tuple[int, int, int],
    right: tuple[int, int, int],
    ratio: float,
) -> tuple[int, int, int]:
    amount = clamp_float(ratio, 0.0, 1.0)
    return tuple(
        int(left[idx] * (1.0 - amount) + right[idx] * amount)
        for idx in range(3)
    )


def alpha_composite(
    image: np.ndarray,
    draw_fn,
    *,
    alpha: float,
) -> None:
    overlay = image.copy()
    draw_fn(overlay)
    cv2.addWeighted(overlay, clamp_float(alpha, 0.0, 1.0), image, 1.0 - clamp_float(alpha, 0.0, 1.0), 0, image)


def draw_rounded_rect(
    image: np.ndarray,
    top_left: tuple[int, int],
    bottom_right: tuple[int, int],
    color: tuple[int, int, int],
    *,
    radius: int = 24,
    thickness: int = -1,
) -> None:
    x1, y1 = top_left
    x2, y2 = bottom_right
    radius = max(0, min(radius, abs(x2 - x1) // 2, abs(y2 - y1) // 2))
    if thickness < 0:
        cv2.rectangle(image, (x1 + radius, y1), (x2 - radius, y2), color, -1, cv2.LINE_AA)
        cv2.rectangle(image, (x1, y1 + radius), (x2, y2 - radius), color, -1, cv2.LINE_AA)
        for center in ((x1 + radius, y1 + radius), (x2 - radius, y1 + radius), (x1 + radius, y2 - radius), (x2 - radius, y2 - radius)):
            cv2.circle(image, center, radius, color, -1, cv2.LINE_AA)
        return

    cv2.line(image, (x1 + radius, y1), (x2 - radius, y1), color, thickness, cv2.LINE_AA)
    cv2.line(image, (x1 + radius, y2), (x2 - radius, y2), color, thickness, cv2.LINE_AA)
    cv2.line(image, (x1, y1 + radius), (x1, y2 - radius), color, thickness, cv2.LINE_AA)
    cv2.line(image, (x2, y1 + radius), (x2, y2 - radius), color, thickness, cv2.LINE_AA)
    cv2.ellipse(image, (x1 + radius, y1 + radius), (radius, radius), 180, 0, 90, color, thickness, cv2.LINE_AA)
    cv2.ellipse(image, (x2 - radius, y1 + radius), (radius, radius), 270, 0, 90, color, thickness, cv2.LINE_AA)
    cv2.ellipse(image, (x1 + radius, y2 - radius), (radius, radius), 90, 0, 90, color, thickness, cv2.LINE_AA)
    cv2.ellipse(image, (x2 - radius, y2 - radius), (radius, radius), 0, 0, 90, color, thickness, cv2.LINE_AA)


def build_gradient_background(
    width: int,
    height: int,
    top_color: tuple[int, int, int],
    bottom_color: tuple[int, int, int],
) -> np.ndarray:
    top = np.array(top_color, dtype=np.float32)
    bottom = np.array(bottom_color, dtype=np.float32)
    ramp = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    column = ((1.0 - ramp) * top + ramp * bottom).astype(np.uint8)
    return np.repeat(column[:, None, :], width, axis=1)


def draw_glow_circle(
    image: np.ndarray,
    center: tuple[int, int],
    radius: int,
    color: tuple[int, int, int],
    *,
    strength: float = 0.18,
) -> None:
    for idx, factor in enumerate((2.2, 1.6, 1.15), start=1):
        current_alpha = strength / (idx * 0.85)
        current_radius = max(8, int(radius * factor))
        alpha_composite(
            image,
            lambda layer, r=current_radius: cv2.circle(layer, center, r, color, -1, cv2.LINE_AA),
            alpha=current_alpha,
        )


def mood_palette(
    mood: str,
    ui: str,
    *,
    dimmed: bool,
) -> dict[str, tuple[int, int, int]]:
    palettes = {
        "inactive": {
            "bg_top": rgb(16, 24, 35),
            "bg_bottom": rgb(7, 11, 18),
            "panel": rgb(24, 32, 46),
            "panel_edge": rgb(74, 92, 118),
            "accent": rgb(146, 184, 212),
            "glow": rgb(96, 137, 172),
            "eye": rgb(217, 236, 246),
            "mouth": rgb(168, 194, 212),
            "cheek": rgb(90, 116, 136),
        },
        "calm": {
            "bg_top": rgb(23, 52, 83),
            "bg_bottom": rgb(8, 21, 38),
            "panel": rgb(18, 41, 64),
            "panel_edge": rgb(84, 180, 236),
            "accent": rgb(106, 224, 255),
            "glow": rgb(64, 178, 255),
            "eye": rgb(233, 248, 255),
            "mouth": rgb(194, 232, 248),
            "cheek": rgb(255, 176, 138),
        },
        "attentive": {
            "bg_top": rgb(15, 63, 92),
            "bg_bottom": rgb(5, 24, 40),
            "panel": rgb(10, 47, 70),
            "panel_edge": rgb(92, 228, 255),
            "accent": rgb(125, 244, 255),
            "glow": rgb(66, 208, 255),
            "eye": rgb(239, 252, 255),
            "mouth": rgb(208, 239, 250),
            "cheek": rgb(255, 196, 150),
        },
        "sleepy": {
            "bg_top": rgb(30, 40, 78),
            "bg_bottom": rgb(12, 17, 34),
            "panel": rgb(22, 28, 55),
            "panel_edge": rgb(155, 166, 255),
            "accent": rgb(196, 202, 255),
            "glow": rgb(114, 124, 228),
            "eye": rgb(232, 237, 255),
            "mouth": rgb(214, 222, 255),
            "cheek": rgb(176, 164, 228),
        },
        "alert": {
            "bg_top": rgb(118, 31, 15),
            "bg_bottom": rgb(55, 12, 8),
            "panel": rgb(82, 22, 15),
            "panel_edge": rgb(255, 176, 107),
            "accent": rgb(255, 216, 124),
            "glow": rgb(255, 90, 55),
            "eye": rgb(255, 245, 225),
            "mouth": rgb(255, 214, 194),
            "cheek": rgb(255, 134, 102),
        },
        "startled": {
            "bg_top": rgb(14, 66, 100),
            "bg_bottom": rgb(6, 30, 47),
            "panel": rgb(10, 52, 79),
            "panel_edge": rgb(255, 202, 120),
            "accent": rgb(255, 225, 143),
            "glow": rgb(254, 126, 75),
            "eye": rgb(255, 248, 235),
            "mouth": rgb(255, 232, 224),
            "cheek": rgb(255, 164, 144),
        },
        "confused": {
            "bg_top": rgb(78, 63, 22),
            "bg_bottom": rgb(31, 23, 8),
            "panel": rgb(61, 46, 16),
            "panel_edge": rgb(244, 217, 120),
            "accent": rgb(252, 229, 141),
            "glow": rgb(209, 168, 59),
            "eye": rgb(255, 245, 208),
            "mouth": rgb(246, 228, 186),
            "cheek": rgb(210, 162, 112),
        },
        "welcome": {
            "bg_top": rgb(15, 77, 74),
            "bg_bottom": rgb(6, 37, 35),
            "panel": rgb(10, 62, 58),
            "panel_edge": rgb(111, 255, 227),
            "accent": rgb(160, 255, 226),
            "glow": rgb(76, 237, 193),
            "eye": rgb(240, 255, 247),
            "mouth": rgb(214, 248, 226),
            "cheek": rgb(255, 188, 167),
        },
        "happy": {
            "bg_top": rgb(127, 54, 42),
            "bg_bottom": rgb(63, 20, 22),
            "panel": rgb(102, 39, 37),
            "panel_edge": rgb(255, 183, 143),
            "accent": rgb(255, 221, 171),
            "glow": rgb(255, 119, 96),
            "eye": rgb(255, 245, 236),
            "mouth": rgb(255, 227, 212),
            "cheek": rgb(255, 152, 148),
        },
    }
    palette = dict(palettes.get(mood, palettes["calm"]))
    if ui == "AlertUI":
        palette["panel_edge"] = mix_color(palette["panel_edge"], rgb(255, 128, 92), 0.42)
        palette["accent"] = mix_color(palette["accent"], rgb(255, 220, 170), 0.32)
    elif ui == "GameUI":
        palette["panel_edge"] = mix_color(palette["panel_edge"], rgb(152, 252, 177), 0.45)
        palette["accent"] = mix_color(palette["accent"], rgb(220, 255, 176), 0.28)
    elif ui == "CameraUI":
        palette["panel_edge"] = mix_color(palette["panel_edge"], rgb(255, 236, 163), 0.35)
        palette["accent"] = mix_color(palette["accent"], rgb(255, 240, 210), 0.18)
    if dimmed:
        for key, color in list(palette.items()):
            palette[key] = scale_color(color, 0.48 if key.startswith("bg") else 0.55)
    return palette


@lru_cache(maxsize=1)
def load_expression_assets() -> dict[str, np.ndarray]:
    assets: dict[str, np.ndarray] = {}
    root = REPO_ROOT / "assets" / "expressions"
    if not root.exists():
        return assets
    for path in sorted(root.glob("*.png")):
        image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if image is not None:
            if image.shape[1] != 1024 or image.shape[0] != 600:
                image = cv2.resize(image, (1024, 600), interpolation=cv2.INTER_AREA)
            assets[path.stem] = image
    return assets


def recent_task_event(rio: RioOrchestrator, kind: ActionKind) -> Event | None:
    for event in reversed(rio.event_log):
        if event.topic not in {topics.TASK_SUCCEEDED, topics.TASK_FAILED}:
            continue
        if event.payload.get("kind") == kind.value:
            return event
    return None


def choose_face_asset_key(
    rio: RioOrchestrator,
    render_frame: Any,
) -> str:
    snapshot = rio.store.snapshot()
    assets = load_expression_assets()
    overlay_key = Path(render_frame.overlay.name).stem if render_frame.overlay.name else ""

    def pick(*candidates: str) -> str:
        for name in candidates:
            if name in assets:
                return name
        return candidates[-1]

    photo_task = recent_task_event(rio, ActionKind.PHOTO)
    if photo_task is not None and photo_task.topic == topics.TASK_SUCCEEDED and is_recent_event(photo_task, within_ms=900):
        return pick("photo_snap", "happy")

    smarthome_result = find_recent_event(rio, topics.SMARTHOME_RESULT)
    if smarthome_result is not None and is_recent_event(smarthome_result) and not smarthome_result.payload.get("ok", True):
        return pick("smarthome_fail", "confused")

    if snapshot.activity_state == ActivityState.EXECUTING:
        kind = snapshot.extended.active_executing_kind
        if kind == ActionKind.PHOTO:
            return pick("photo_ready", "attentive")
        if kind == ActionKind.GAME:
            return pick("game_face", "attentive")
        if kind == ActionKind.DANCE:
            return pick("dance_face", "happy")
        if kind == ActionKind.WEATHER:
            return pick("weather_face", "attentive")

    if render_frame.ui == "CameraUI":
        return pick("photo_ready", "attentive")
    if render_frame.ui == "GameUI":
        return pick("game_face", "attentive")

    if overlay_key in {"petting", "welcome", "startled"}:
        return pick(overlay_key, render_frame.face.mood)
    if overlay_key == "sleep":
        return pick("sleepy")

    if render_frame.face.mood == "inactive":
        return pick("sleepy")
    return pick(render_frame.face.mood, "calm")


def asset_transition_keys(asset_key: str, *, now_s: float) -> tuple[str | None, str, float]:
    state = _FACE_ASSET_TRANSITION
    if state["current"] != asset_key:
        state["previous"] = state["current"]
        state["current"] = asset_key
        state["changed_at"] = now_s
    progress = clamp_float((now_s - float(state["changed_at"])) / 0.26, 0.0, 1.0)
    previous = state["previous"] if progress < 1.0 else None
    if progress >= 1.0:
        state["previous"] = None
    return previous, asset_key, progress


def composite_panel_rgba(
    canvas: np.ndarray,
    panel_rgba: np.ndarray,
    rect: tuple[int, int, int, int],
) -> None:
    x1, y1, x2, y2 = rect
    target = canvas[y1:y2, x1:x2]
    rgb_channels = panel_rgba[:, :, :3].astype(np.float32)
    if panel_rgba.shape[2] == 4:
        alpha = (panel_rgba[:, :, 3:4].astype(np.float32) / 255.0)
    else:
        alpha = np.ones((*panel_rgba.shape[:2], 1), dtype=np.float32)
    target_float = target.astype(np.float32)
    blended = rgb_channels * alpha + target_float * (1.0 - alpha)
    target[:] = blended.astype(np.uint8)


def make_asset_panel(
    asset_rgba: np.ndarray,
    *,
    panel_size: tuple[int, int],
    scale: float,
    shift: tuple[int, int],
    alpha: float,
    dimmed: bool,
) -> np.ndarray:
    panel_w, panel_h = panel_size
    scaled_w = max(8, int(panel_w * scale))
    scaled_h = max(8, int(panel_h * scale))
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
    resized = cv2.resize(asset_rgba, (scaled_w, scaled_h), interpolation=interpolation)

    panel = np.zeros((panel_h, panel_w, 4), dtype=np.uint8)
    panel[:, :, :3] = ASSET_FACE_BG
    panel[:, :, 3] = 255

    offset_x = (panel_w - scaled_w) // 2 + shift[0]
    offset_y = (panel_h - scaled_h) // 2 + shift[1]

    src_x1 = max(0, -offset_x)
    src_y1 = max(0, -offset_y)
    dst_x1 = max(0, offset_x)
    dst_y1 = max(0, offset_y)
    copy_w = min(scaled_w - src_x1, panel_w - dst_x1)
    copy_h = min(scaled_h - src_y1, panel_h - dst_y1)
    if copy_w > 0 and copy_h > 0:
        src = resized[src_y1:src_y1 + copy_h, src_x1:src_x1 + copy_w]
        panel[dst_y1:dst_y1 + copy_h, dst_x1:dst_x1 + copy_w] = src

    if alpha < 1.0:
        panel[:, :, 3] = (panel[:, :, 3].astype(np.float32) * alpha).astype(np.uint8)

    if dimmed:
        panel[:, :, :3] = (panel[:, :, :3].astype(np.float32) * 0.62).astype(np.uint8)
    return panel


def draw_asset_blink_overlay(
    image: np.ndarray,
    rect: tuple[int, int, int, int],
    *,
    blink: float,
) -> None:
    if blink <= 0.08:
        return
    x1, y1, x2, y2 = rect
    eye_cy = int(y1 + (y2 - y1) * 0.376)
    eye_w = int((x2 - x1) * 0.095)
    eye_h = int((y2 - y1) * 0.168)
    bar_h = max(2, int(eye_h * blink))
    for cx_ratio in (0.261, 0.739):
        cx = int(x1 + (x2 - x1) * cx_ratio)
        cv2.rectangle(
            image,
            (cx - eye_w // 2, eye_cy - bar_h // 2),
            (cx + eye_w // 2, eye_cy + bar_h // 2),
            ASSET_FACE_BG,
            -1,
            cv2.LINE_AA,
        )


def draw_face_asset_panel(
    canvas: np.ndarray,
    *,
    rect: tuple[int, int, int, int],
    asset_key: str,
    render_frame: Any,
    now_s: float,
) -> bool:
    assets = load_expression_assets()
    if asset_key not in assets:
        return False

    x1, y1, x2, y2 = rect
    panel_rect = (x1 + 16, y1 + 16, x2 - 16, y2 - 16)
    panel_w = panel_rect[2] - panel_rect[0]
    panel_h = panel_rect[3] - panel_rect[1]
    shift = (
        int(render_frame.face.eye_offset[0] * 1.5),
        int(render_frame.face.eye_offset[1] * 1.2 + math.sin(now_s * 1.4) * 4.0),
    )
    scale = 1.0 + 0.02 * math.sin(now_s * 1.2)

    previous_key, current_key, progress = asset_transition_keys(asset_key, now_s=now_s)
    current_panel = make_asset_panel(
        assets[current_key],
        panel_size=(panel_w, panel_h),
        scale=scale,
        shift=shift,
        alpha=1.0 if previous_key is None else progress,
        dimmed=render_frame.face.dimmed,
    )

    if previous_key is not None and previous_key in assets:
        previous_panel = make_asset_panel(
            assets[previous_key],
            panel_size=(panel_w, panel_h),
            scale=scale,
            shift=shift,
            alpha=1.0 - progress,
            dimmed=render_frame.face.dimmed,
        )
        composite_panel_rgba(canvas, previous_panel, panel_rect)

    composite_panel_rgba(canvas, current_panel, panel_rect)

    if current_key in {"calm", "attentive"}:
        draw_asset_blink_overlay(canvas, panel_rect, blink=blink_amount(now_s, current_key))

    return True


def blink_amount(now_s: float, mood: str) -> float:
    if mood == "inactive":
        return 0.72 + 0.18 * math.sin(now_s * 0.45)
    if mood == "sleepy":
        period = 3.1
        width = 0.22
    elif mood in {"alert", "startled"}:
        period = 6.2
        width = 0.06
    elif mood == "happy":
        period = 4.2
        width = 0.12
    else:
        period = 4.8
        width = 0.09

    phase = (now_s / period) % 1.0
    centers = [0.05]
    if mood in {"happy", "welcome"}:
        centers.append(0.11)
    blink = 0.0
    for center in centers:
        distance = abs(phase - center)
        blink = max(blink, max(0.0, 1.0 - distance / width))
    return clamp_float(blink, 0.0, 1.0)


def draw_heart(
    image: np.ndarray,
    center: tuple[int, int],
    size: int,
    color: tuple[int, int, int],
    *,
    thickness: int = -1,
) -> None:
    radius = max(4, size // 3)
    left = (center[0] - radius, center[1] - radius // 2)
    right = (center[0] + radius, center[1] - radius // 2)
    bottom = np.array(
        [
            [center[0] - size, center[1] - radius // 2],
            [center[0] + size, center[1] - radius // 2],
            [center[0], center[1] + size],
        ],
        dtype=np.int32,
    )
    cv2.circle(image, left, radius, color, thickness, cv2.LINE_AA)
    cv2.circle(image, right, radius, color, thickness, cv2.LINE_AA)
    cv2.fillConvexPoly(image, bottom, color, cv2.LINE_AA)


def draw_star(
    image: np.ndarray,
    center: tuple[int, int],
    radius: int,
    color: tuple[int, int, int],
    *,
    thickness: int = 2,
) -> None:
    cv2.line(image, (center[0] - radius, center[1]), (center[0] + radius, center[1]), color, thickness, cv2.LINE_AA)
    cv2.line(image, (center[0], center[1] - radius), (center[0], center[1] + radius), color, thickness, cv2.LINE_AA)
    cv2.line(
        image,
        (center[0] - radius // 2, center[1] - radius // 2),
        (center[0] + radius // 2, center[1] + radius // 2),
        color,
        max(1, thickness - 1),
        cv2.LINE_AA,
    )
    cv2.line(
        image,
        (center[0] - radius // 2, center[1] + radius // 2),
        (center[0] + radius // 2, center[1] - radius // 2),
        color,
        max(1, thickness - 1),
        cv2.LINE_AA,
    )


def draw_mouth(
    image: np.ndarray,
    center: tuple[int, int],
    mood: str,
    palette: dict[str, tuple[int, int, int]],
    *,
    now_s: float,
    width: int,
    height: int,
) -> None:
    mouth_color = palette["mouth"]
    accent = palette["accent"]
    if mood == "startled":
        radius = max(10, width // 8)
        cv2.circle(image, center, radius, mouth_color, 4, cv2.LINE_AA)
        cv2.circle(image, center, max(3, radius // 2), scale_color(palette["panel"], 0.55), -1, cv2.LINE_AA)
        return
    if mood == "sleepy":
        rx = max(16, width // 6)
        ry = max(10, height // 3)
        cv2.ellipse(image, center, (rx, ry), 0, 0, 360, mouth_color, 4, cv2.LINE_AA)
        cv2.ellipse(image, center, (max(6, rx - 6), max(4, ry - 6)), 0, 0, 360, scale_color(palette["panel"], 0.72), -1, cv2.LINE_AA)
        return
    if mood == "confused":
        points = []
        for idx in range(6):
            x = int(center[0] - width // 2 + idx * (width / 5.0))
            y = int(center[1] + math.sin(now_s * 4.0 + idx * 0.9) * 5.0)
            points.append((x, y))
        cv2.polylines(image, [np.array(points, dtype=np.int32)], False, mouth_color, 4, cv2.LINE_AA)
        return
    if mood == "alert":
        cv2.line(image, (center[0] - width // 3, center[1]), (center[0] + width // 3, center[1]), mouth_color, 5, cv2.LINE_AA)
        cv2.circle(image, (center[0] + width // 2, center[1] - height), max(4, width // 10), accent, -1, cv2.LINE_AA)
        return
    if mood in {"happy", "welcome"}:
        rx = max(22, width // 2)
        ry = max(14, height)
        cv2.ellipse(image, center, (rx, ry), 0, 10, 170, mouth_color, 5, cv2.LINE_AA)
        if mood == "happy":
            tongue_center = (center[0], center[1] + max(6, height // 2))
            cv2.ellipse(image, tongue_center, (max(10, width // 6), max(6, height // 3)), 0, 0, 180, palette["cheek"], -1, cv2.LINE_AA)
        return
    curve = 22 if mood == "calm" else 12
    rx = max(18, width // 2)
    ry = max(8, height // 2)
    cv2.ellipse(image, center, (rx, ry), 0, 20, 160, mouth_color, 4, cv2.LINE_AA)
    if mood == "attentive":
        cv2.line(image, (center[0] - rx // 3, center[1] + curve // 10), (center[0] + rx // 3, center[1] + curve // 10), accent, 2, cv2.LINE_AA)


def draw_eye(
    image: np.ndarray,
    center: tuple[int, int],
    mood: str,
    palette: dict[str, tuple[int, int, int]],
    *,
    eye_width: int,
    eye_height: int,
    open_ratio: float,
    pupil_offset: tuple[int, int],
    eyebrow_tilt: int = 0,
) -> None:
    white = palette["eye"]
    accent = palette["accent"]
    panel = palette["panel"]
    eye_open_px = max(4, int(eye_height * clamp_float(open_ratio, 0.08, 1.15)))

    if mood == "happy":
        cv2.ellipse(image, center, (eye_width, max(4, eye_height // 2)), 0, 205, 335, white, 7, cv2.LINE_AA)
    elif mood == "inactive":
        cv2.line(image, (center[0] - eye_width, center[1]), (center[0] + eye_width, center[1]), scale_color(white, 0.8), 6, cv2.LINE_AA)
    else:
        cv2.ellipse(image, center, (eye_width, eye_open_px), 0, 0, 360, white, -1, cv2.LINE_AA)
        cv2.ellipse(image, center, (eye_width, eye_open_px), 0, 0, 360, accent, 3, cv2.LINE_AA)
        if open_ratio > 0.18:
            iris_center = (
                center[0] + int(clamp_float(pupil_offset[0], -eye_width * 0.45, eye_width * 0.45)),
                center[1] + int(clamp_float(pupil_offset[1], -eye_open_px * 0.35, eye_open_px * 0.35)),
            )
            iris_radius = max(7, int(min(eye_width, eye_open_px) * 0.52))
            cv2.circle(image, iris_center, iris_radius, scale_color(accent, 0.95), -1, cv2.LINE_AA)
            cv2.circle(image, iris_center, max(3, iris_radius // 2), scale_color(panel, 0.28), -1, cv2.LINE_AA)
            highlight = (iris_center[0] - max(2, iris_radius // 3), iris_center[1] - max(2, iris_radius // 3))
            cv2.circle(image, highlight, max(2, iris_radius // 4), rgb(255, 255, 255), -1, cv2.LINE_AA)

    brow_y = center[1] - eye_height - 16
    left = (center[0] - eye_width, brow_y + eyebrow_tilt)
    right = (center[0] + eye_width, brow_y - eyebrow_tilt)
    cv2.line(image, left, right, scale_color(accent, 0.86), 5, cv2.LINE_AA)


def draw_ui_overlay(
    image: np.ndarray,
    *,
    face_rect: tuple[int, int, int, int],
    ui: str,
    palette: dict[str, tuple[int, int, int]],
    search_indicator: bool,
    overlay_name: str | None,
    now_s: float,
    gesture: str | None,
) -> None:
    x1, y1, x2, y2 = face_rect
    accent = palette["accent"]
    panel_edge = palette["panel_edge"]
    overlay_key = Path(overlay_name).stem if overlay_name else ""
    pulse = 0.5 + 0.5 * math.sin(now_s * 4.2)

    if ui == "ListeningUI":
        alpha_composite(
            image,
            lambda layer: cv2.circle(layer, ((x1 + x2) // 2, (y1 + y2) // 2), int((x2 - x1) * (0.38 + pulse * 0.06)), accent, 7, cv2.LINE_AA),
            alpha=0.22,
        )
        if search_indicator:
            sweep_x = int(x1 + ((math.sin(now_s * 2.7) + 1.0) * 0.5) * (x2 - x1))
            alpha_composite(
                image,
                lambda layer: cv2.rectangle(layer, (max(x1, sweep_x - 16), y1 + 24), (min(x2, sweep_x + 16), y2 - 24), accent, -1, cv2.LINE_AA),
                alpha=0.12,
            )

    if ui == "CameraUI" or overlay_key == "camera_countdown":
        bracket_color = mix_color(panel_edge, rgb(255, 238, 178), 0.4)
        for sx, sy in ((x1 + 34, y1 + 34), (x2 - 34, y1 + 34), (x1 + 34, y2 - 34), (x2 - 34, y2 - 34)):
            dx = 28 if sx < (x1 + x2) // 2 else -28
            dy = 28 if sy < (y1 + y2) // 2 else -28
            cv2.line(image, (sx, sy), (sx + dx, sy), bracket_color, 4, cv2.LINE_AA)
            cv2.line(image, (sx, sy), (sx, sy + dy), bracket_color, 4, cv2.LINE_AA)
        cv2.circle(image, (x2 - 52, y1 + 52), 10, rgb(255, 96, 82), -1, cv2.LINE_AA)

    if ui == "GameUI" or overlay_key == "game_direction":
        arrow_color = mix_color(accent, rgb(184, 255, 168), 0.22)
        cy = (y1 + y2) // 2
        left_arrow = np.array([[x1 + 36, cy], [x1 + 90, cy - 30], [x1 + 90, cy + 30]], dtype=np.int32)
        right_arrow = np.array([[x2 - 36, cy], [x2 - 90, cy - 30], [x2 - 90, cy + 30]], dtype=np.int32)
        cv2.polylines(image, [left_arrow], True, arrow_color, 4, cv2.LINE_AA)
        cv2.polylines(image, [right_arrow], True, arrow_color, 4, cv2.LINE_AA)
        if gesture in {"head_left", "head_right"}:
            badge_x = x1 + 86 if gesture == "head_left" else x2 - 86
            cv2.circle(image, (badge_x, cy), 18, arrow_color, -1, cv2.LINE_AA)

    if ui == "AlertUI":
        alert_color = mix_color(panel_edge, rgb(255, 115, 92), 0.6)
        thickness = 4 + int(pulse * 4)
        draw_rounded_rect(image, (x1 - 8, y1 - 8), (x2 + 8, y2 + 8), alert_color, radius=40, thickness=thickness)

    if ui == "SleepUI":
        for idx in range(3):
            pos = (x2 - 150 + idx * 26, y1 + 88 - idx * 18)
            cv2.putText(image, "Z", pos, cv2.FONT_HERSHEY_DUPLEX, 0.9 + idx * 0.12, scale_color(accent, 1.05), 2, cv2.LINE_AA)
        draw_star(image, (x1 + 90, y1 + 78), 12, scale_color(accent, 1.08))

    if overlay_key in {"petting", "welcome", "peekaboo", "wave"}:
        for idx in range(3):
            heart_center = (x1 + 96 + idx * 42, y1 + 96 - int(math.sin(now_s * 2.8 + idx) * 8.0))
            draw_heart(image, heart_center, 16, scale_color(palette["cheek"], 1.06))

    if overlay_key == "smarthome_badge":
        badge_center = (x2 - 84, y2 - 74)
        cv2.circle(image, badge_center, 34, mix_color(panel_edge, rgb(83, 255, 197), 0.25), -1, cv2.LINE_AA)
        home = np.array(
            [
                [badge_center[0] - 18, badge_center[1] + 6],
                [badge_center[0] - 18, badge_center[1] - 6],
                [badge_center[0], badge_center[1] - 22],
                [badge_center[0] + 18, badge_center[1] - 6],
                [badge_center[0] + 18, badge_center[1] + 6],
            ],
            dtype=np.int32,
        )
        cv2.polylines(image, [home], False, rgb(255, 255, 255), 3, cv2.LINE_AA)
        cv2.rectangle(image, (badge_center[0] - 10, badge_center[1] + 2), (badge_center[0] + 10, badge_center[1] + 20), rgb(255, 255, 255), 3, cv2.LINE_AA)

    if overlay_key == "finger_gun":
        cv2.putText(image, "BANG!", (x1 + 52, y1 + 82), cv2.FONT_HERSHEY_DUPLEX, 1.0, rgb(255, 228, 148), 2, cv2.LINE_AA)


def draw_robot_face(
    canvas: np.ndarray,
    rio: RioOrchestrator,
    *,
    face_rect: tuple[int, int, int, int],
    now_s: float,
    render_frame: Any,
    details: dict[str, str],
    last_gesture: str | None,
) -> None:
    snapshot = rio.store.snapshot()
    palette = mood_palette(render_frame.face.mood, render_frame.ui, dimmed=render_frame.face.dimmed)
    x1, y1, x2, y2 = face_rect
    face_width = x2 - x1
    face_height = y2 - y1
    center_x = (x1 + x2) // 2
    center_y = (y1 + y2) // 2

    alpha_composite(
        canvas,
        lambda layer: draw_rounded_rect(layer, (x1 + 18, y1 + 26), (x2 + 10, y2 + 36), rgb(4, 10, 18), radius=48),
        alpha=0.32,
    )
    draw_rounded_rect(canvas, (x1, y1), (x2, y2), scale_color(palette["panel"], 0.96), radius=48)
    draw_rounded_rect(canvas, (x1, y1), (x2, y2), palette["panel_edge"], radius=48, thickness=4)

    asset_key = choose_face_asset_key(rio, render_frame)
    if draw_face_asset_panel(
        canvas,
        rect=face_rect,
        asset_key=asset_key,
        render_frame=render_frame,
        now_s=now_s,
    ):
        draw_ui_overlay(
            canvas,
            face_rect=face_rect,
            ui=render_frame.ui,
            palette=palette,
            search_indicator=render_frame.hud.search_indicator,
            overlay_name=render_frame.overlay.name,
            now_s=now_s,
            gesture=last_gesture,
        )

        badge_text = details["current_action"]
        badge_w = min(face_width - 60, max(260, len(badge_text) * 11))
        badge_rect = (center_x - badge_w // 2, y2 - 86, center_x + badge_w // 2, y2 - 34)
        alpha_composite(
            canvas,
            lambda layer: draw_rounded_rect(layer, (badge_rect[0], badge_rect[1]), (badge_rect[2], badge_rect[3]), scale_color(palette["panel"], 0.52), radius=24),
            alpha=0.54,
        )
        draw_rounded_rect(canvas, (badge_rect[0], badge_rect[1]), (badge_rect[2], badge_rect[3]), scale_color(palette["panel_edge"], 0.74), radius=24, thickness=2)
        cv2.putText(
            canvas,
            trim_text(badge_text, limit=38),
            (badge_rect[0] + 18, badge_rect[1] + 34),
            cv2.FONT_HERSHEY_DUPLEX,
            0.75,
            rgb(245, 248, 250),
            1,
            cv2.LINE_AA,
        )
        return

    bob = math.sin(now_s * 1.7) * 5.0 + math.sin(now_s * 0.65 + 0.6) * 3.0
    center_y = int(center_y + bob)

    draw_glow_circle(canvas, (center_x, center_y - 24), int(face_width * 0.26), palette["glow"], strength=0.18)

    ear_color = scale_color(palette["panel"], 1.12)
    ear_glow = scale_color(palette["accent"], 0.72)
    left_ear = (x1 + face_width // 5, y1 + 88 + int(math.sin(now_s * 2.2) * 4.0))
    right_ear = (x2 - face_width // 5, y1 + 88 + int(math.sin(now_s * 2.2 + 1.1) * 4.0))
    for center in (left_ear, right_ear):
        draw_glow_circle(canvas, center, 26, ear_glow, strength=0.12)
        cv2.circle(canvas, center, 26, ear_color, -1, cv2.LINE_AA)
        cv2.circle(canvas, center, 12, scale_color(palette["accent"], 0.92), -1, cv2.LINE_AA)

    draw_rounded_rect(canvas, (x1, y1), (x2, y2), palette["panel"], radius=48)
    alpha_composite(
        canvas,
        lambda layer: draw_rounded_rect(layer, (x1 + 14, y1 + 14), (x2 - 14, y2 - 14), scale_color(palette["panel_edge"], 0.34), radius=40),
        alpha=0.14,
    )
    draw_rounded_rect(canvas, (x1, y1), (x2, y2), palette["panel_edge"], radius=48, thickness=4)

    eye_spacing = face_width // 4
    eye_y = center_y - face_height // 10
    eye_width = max(32, face_width // 11)
    eye_height = max(26, face_height // 10)
    offset_x, offset_y = render_frame.face.eye_offset
    subtle_x = math.sin(now_s * 0.8) * 1.5
    subtle_y = math.cos(now_s * 0.95) * 1.2
    pupil_offset = (int(offset_x * 1.65 + subtle_x), int(offset_y * 1.45 + subtle_y))

    blink = blink_amount(now_s, render_frame.face.mood)
    base_open = {
        "inactive": 0.16,
        "calm": 0.92,
        "attentive": 1.0,
        "sleepy": 0.38,
        "alert": 1.04,
        "startled": 1.08,
        "confused": 0.78,
        "welcome": 0.96,
        "happy": 0.28,
    }.get(render_frame.face.mood, 0.9)
    open_left = base_open * (1.0 - blink * 0.96)
    open_right = base_open * (1.0 - blink * 0.92)
    if render_frame.face.mood == "confused":
        open_left *= 0.72
    if render_frame.face.mood == "sleepy":
        open_right *= 0.88

    eyebrow_tilt = {
        "calm": -2,
        "attentive": 1,
        "sleepy": 8,
        "alert": -8,
        "startled": -10,
        "confused": 5,
        "welcome": -3,
        "happy": -4,
        "inactive": 2,
    }.get(render_frame.face.mood, 0)

    left_eye = (center_x - eye_spacing // 2, eye_y)
    right_eye = (center_x + eye_spacing // 2, eye_y)
    draw_eye(
        canvas,
        left_eye,
        render_frame.face.mood,
        palette,
        eye_width=eye_width,
        eye_height=eye_height,
        open_ratio=open_left,
        pupil_offset=pupil_offset,
        eyebrow_tilt=eyebrow_tilt if render_frame.face.mood != "confused" else 9,
    )
    draw_eye(
        canvas,
        right_eye,
        render_frame.face.mood,
        palette,
        eye_width=eye_width,
        eye_height=eye_height,
        open_ratio=open_right,
        pupil_offset=(pupil_offset[0] - 2, pupil_offset[1]),
        eyebrow_tilt=-eyebrow_tilt if render_frame.face.mood == "confused" else eyebrow_tilt,
    )

    mouth_center = (center_x, center_y + face_height // 6)
    draw_mouth(
        canvas,
        mouth_center,
        render_frame.face.mood,
        palette,
        now_s=now_s,
        width=face_width // 5,
        height=face_height // 13,
    )

    if render_frame.face.mood in {"happy", "welcome"}:
        cheek_y = mouth_center[1] - 18
        for cheek_x in (center_x - eye_spacing // 2, center_x + eye_spacing // 2):
            alpha_composite(
                canvas,
                lambda layer, cx=cheek_x: cv2.circle(layer, (cx, cheek_y), 26, palette["cheek"], -1, cv2.LINE_AA),
                alpha=0.22,
            )

    if snapshot.context_state == ContextState.SLEEPY:
        draw_star(canvas, (x1 + 120, y1 + 126), 14, scale_color(palette["accent"], 1.1))
        draw_star(canvas, (x1 + 178, y1 + 88), 10, scale_color(palette["accent"], 0.95))

    if snapshot.active_oneshot is not None and snapshot.active_oneshot.name.value == "happy":
        draw_heart(canvas, (x2 - 92, y1 + 122), 18, scale_color(palette["cheek"], 1.05))
        draw_heart(canvas, (x2 - 138, y1 + 98), 14, scale_color(palette["cheek"], 1.0))

    draw_ui_overlay(
        canvas,
        face_rect=face_rect,
        ui=render_frame.ui,
        palette=palette,
        search_indicator=render_frame.hud.search_indicator,
        overlay_name=render_frame.overlay.name,
        now_s=now_s,
        gesture=last_gesture,
    )

    badge_text = details["current_action"]
    badge_w = min(face_width - 60, max(260, len(badge_text) * 11))
    badge_rect = (center_x - badge_w // 2, y2 - 86, center_x + badge_w // 2, y2 - 34)
    alpha_composite(
        canvas,
        lambda layer: draw_rounded_rect(layer, (badge_rect[0], badge_rect[1]), (badge_rect[2], badge_rect[3]), scale_color(palette["panel"], 0.52), radius=24),
        alpha=0.54,
    )
    draw_rounded_rect(canvas, (badge_rect[0], badge_rect[1]), (badge_rect[2], badge_rect[3]), scale_color(palette["panel_edge"], 0.74), radius=24, thickness=2)
    cv2.putText(
        canvas,
        trim_text(badge_text, limit=38),
        (badge_rect[0] + 18, badge_rect[1] + 34),
        cv2.FONT_HERSHEY_DUPLEX,
        0.75,
        rgb(245, 248, 250),
        1,
        cv2.LINE_AA,
    )


def draw_status_sidebar(
    canvas: np.ndarray,
    *,
    sidebar_rect: tuple[int, int, int, int],
    camera_frame: Any,
    face_event: Event | None,
    rio: RioOrchestrator,
    details: dict[str, str],
    last_gesture: str | None,
    last_input: str | None,
) -> None:
    x1, y1, x2, y2 = sidebar_rect
    sidebar_top = rgb(10, 18, 28)
    sidebar_bottom = rgb(6, 10, 16)
    alpha_composite(
        canvas,
        lambda layer: draw_rounded_rect(layer, (x1, y1), (x2, y2), sidebar_top, radius=36),
        alpha=0.72,
    )
    draw_rounded_rect(canvas, (x1, y1), (x2, y2), rgb(71, 120, 165), radius=36, thickness=2)

    inset_x1, inset_y1 = x1 + 22, y1 + 22
    inset_x2, inset_y2 = x2 - 22, y1 + 22 + 186
    draw_rounded_rect(canvas, (inset_x1, inset_y1), (inset_x2, inset_y2), rgb(18, 28, 42), radius=24)
    if hasattr(camera_frame, "shape"):
        inset = camera_frame.copy()
        inset_h = inset_y2 - inset_y1
        inset_w = inset_x2 - inset_x1
        inset = cv2.resize(inset, (inset_w, inset_h))
        if face_event is not None:
            center = preview_center_to_pixels(inset, tuple(face_event.payload.get("center", (0.5, 0.5))))
            if center is not None:
                cv2.circle(inset, center, 12, rgb(110, 255, 174), 2, cv2.LINE_AA)
                cv2.putText(inset, "face", (center[0] + 12, max(26, center[1] - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, rgb(110, 255, 174), 1, cv2.LINE_AA)
        canvas[inset_y1:inset_y2, inset_x1:inset_x2] = inset
    draw_rounded_rect(canvas, (inset_x1, inset_y1), (inset_x2, inset_y2), rgb(93, 162, 224), radius=24, thickness=2)
    cv2.putText(canvas, "Live webcam", (inset_x1 + 14, inset_y1 + 24), cv2.FONT_HERSHEY_DUPLEX, 0.55, rgb(233, 246, 255), 1, cv2.LINE_AA)

    cards = [
        ("Doing", trim_text(details["current_action"], limit=30)),
        ("Intent", trim_text(details["last_intent"], limit=30)),
        ("Result", trim_text(details["last_result"], limit=30)),
        ("Gesture", last_gesture or "-"),
        ("Input", trim_text(last_input, limit=30)),
        ("HTTP", f"{details['http_sent']} / {details['http_status']}"),
        ("Payload", trim_text(details["http_payload"], limit=30)),
    ]

    card_y = inset_y2 + 24
    for title, value in cards:
        card_h = 52
        alpha_composite(
            canvas,
            lambda layer, top=card_y, h=card_h: draw_rounded_rect(layer, (x1 + 18, top), (x2 - 18, top + h), sidebar_bottom, radius=18),
            alpha=0.68,
        )
        cv2.putText(canvas, title, (x1 + 34, card_y + 19), cv2.FONT_HERSHEY_DUPLEX, 0.46, rgb(132, 189, 234), 1, cv2.LINE_AA)
        cv2.putText(canvas, value, (x1 + 34, card_y + 41), cv2.FONT_HERSHEY_DUPLEX, 0.56, rgb(243, 247, 250), 1, cv2.LINE_AA)
        card_y += card_h + 10

    footer = rio.renderer.history[-1].hud.message if rio.renderer.history else "-"
    cv2.putText(canvas, "HUD", (x1 + 34, y2 - 52), cv2.FONT_HERSHEY_DUPLEX, 0.46, rgb(132, 189, 234), 1, cv2.LINE_AA)
    cv2.putText(canvas, trim_text(footer or "-", limit=28), (x1 + 34, y2 - 24), cv2.FONT_HERSHEY_DUPLEX, 0.62, rgb(255, 230, 181), 1, cv2.LINE_AA)


def show_preview(
    frame: Any,
    rio: RioOrchestrator,
    *,
    face_event: Event | None,
    last_gesture: str | None,
    last_input: str | None,
    service_mode: str,
    debug: bool,
) -> bool:
    global _PREVIEW_WINDOW_MODE
    if not hasattr(frame, "copy"):
        return False

    snapshot = rio.store.snapshot()
    render_frame = rio.renderer.history[-1] if rio.renderer.history else None
    if render_frame is None:
        return False

    details = describe_runtime_snapshot(rio, service_mode=service_mode)
    now_s = time.time()
    frame_h, frame_w = frame.shape[:2]
    canvas_h = max(720, frame_h if debug else 800)
    canvas_w = max(1180, int(canvas_h * 1.72)) if debug else max(1280, int(canvas_h * 16 / 9))

    palette = mood_palette(render_frame.face.mood, render_frame.ui, dimmed=render_frame.face.dimmed)
    preview = build_gradient_background(canvas_w, canvas_h, palette["bg_top"], palette["bg_bottom"])

    for idx in range(3):
        orb_x = int(canvas_w * (0.18 + idx * 0.24) + math.sin(now_s * (0.55 + idx * 0.2)) * 42.0)
        orb_y = int(canvas_h * (0.16 + idx * 0.21) + math.cos(now_s * (0.75 + idx * 0.18)) * 26.0)
        draw_glow_circle(preview, (orb_x, orb_y), 48 + idx * 18, scale_color(palette["glow"], 0.88), strength=0.11)

    if debug:
        face_rect = (54, 52, int(canvas_w * 0.68), canvas_h - 54)
        sidebar_rect = (face_rect[2] + 26, 52, canvas_w - 32, canvas_h - 54)
    else:
        horizontal_margin = max(36, canvas_w // 18)
        vertical_margin = max(30, canvas_h // 20)
        face_rect = (horizontal_margin, vertical_margin, canvas_w - horizontal_margin, canvas_h - vertical_margin)
        sidebar_rect = (0, 0, 0, 0)

    draw_robot_face(
        preview,
        rio,
        face_rect=face_rect,
        now_s=now_s,
        render_frame=render_frame,
        details=details,
        last_gesture=last_gesture,
    )
    if debug:
        draw_status_sidebar(
            preview,
            sidebar_rect=sidebar_rect,
            camera_frame=frame,
            face_event=face_event,
            rio=rio,
            details=details,
            last_gesture=last_gesture,
            last_input=last_input,
        )

        context_line = f"{snapshot.context_state.value} / {snapshot.activity_state.value}"
        cv2.putText(preview, "RIO live display", (72, 46), cv2.FONT_HERSHEY_DUPLEX, 0.72, rgb(229, 239, 245), 1, cv2.LINE_AA)
        cv2.putText(preview, context_line, (canvas_w - 280, 42), cv2.FONT_HERSHEY_DUPLEX, 0.62, rgb(210, 229, 242), 1, cv2.LINE_AA)

    desired_mode = "debug" if debug else "fullscreen"
    if _PREVIEW_WINDOW_MODE != desired_mode:
        cv2.namedWindow("RIO Live Display", cv2.WINDOW_NORMAL)
        if debug:
            cv2.setWindowProperty("RIO Live Display", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
            cv2.resizeWindow("RIO Live Display", min(canvas_w, 1440), min(canvas_h, 900))
        else:
            cv2.setWindowProperty("RIO Live Display", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        _PREVIEW_WINDOW_MODE = desired_mode
    cv2.imshow("RIO Live Display", preview)
    key = cv2.waitKey(1) & 0xFF
    return key in {27, ord("q")}


def process_frame(
    rio: RioOrchestrator,
    stream: CameraStream,
    face_detector: FaceDetector,
    face_tracker: FaceTracker,
    gesture_detector: GestureDetector,
    *,
    had_face: bool,
) -> tuple[bool, str | None, Any, Event | None]:
    now = datetime.now(timezone.utc)
    frame = stream.read()
    face_event = face_detector.detect(frame, now=now)
    last_gesture: str | None = None

    if face_event is not None:
        had_face = True
        rio.process_event(face_event)
        center = tuple(face_event.payload.get("center", (0.5, 0.5)))
        for moved in face_tracker.update(center, now=now):
            rio.process_event(moved)
    elif had_face:
        had_face = False
        rio.process_event(Event.create(topics.VISION_FACE_LOST, "live.interaction", timestamp=now))

    for gesture_event in gesture_detector.detect(frame, now=now):
        last_gesture = str(gesture_event.payload.get("gesture"))
        rio.process_event(gesture_event)

    return had_face, last_gesture, frame, face_event


def process_console_line(
    rio: RioOrchestrator,
    terminal_voice: TerminalVoiceInput,
    line: str,
) -> tuple[bool, bool, str | None]:
    text = line.strip()
    if not text:
        return False, False, None

    now = datetime.now(timezone.utc)
    if text in {"/quit", "/exit"}:
        return True, False, text
    if text == "/help":
        print_help()
        return False, False, text
    if text == "/status":
        return False, True, text
    if text == "/tap":
        rio.process_event(Event.create(topics.TOUCH_TAP_DETECTED, "live.console", timestamp=now))
        return False, True, text
    if text == "/stroke":
        rio.process_event(Event.create(topics.TOUCH_STROKE_DETECTED, "live.console", timestamp=now))
        return False, True, text
    if text.startswith("/gesture"):
        gesture = text.partition(" ")[2].strip()
        if not gesture:
            print("e.g.: /gesture wave")
            return False, False, text
        rio.process_event(
            Event.create(
                topics.VISION_GESTURE_DETECTED,
                "live.console",
                payload={"gesture": gesture, "confidence": 1.0, "synthetic": True},
                timestamp=now,
            )
        )
        return False, True, text
    if text.startswith("/face"):
        position = text.partition(" ")[2].strip() or "center"
        if position == "lost":
            rio.process_event(Event.create(topics.VISION_FACE_LOST, "live.console", timestamp=now))
            return False, True, text
        center_map = {
            "left": (0.2, 0.5),
            "center": (0.5, 0.5),
            "right": (0.8, 0.5),
        }
        center = center_map.get(position)
        if center is None:
            print("e.g.: /face left | /face center | /face right | /face lost")
            return False, False, text
        rio.process_event(
            Event.create(
                topics.VISION_FACE_DETECTED,
                "live.console",
                payload={"center": center, "confidence": 1.0, "synthetic": True},
                timestamp=now,
            )
        )
        return False, True, text
    if text.startswith("/timer"):
        label = text.partition(" ")[2].strip() or "console"
        rio.process_event(
            Event.create(
                topics.TIMER_EXPIRED,
                "live.console",
                payload={"label": label},
                timestamp=now,
            )
        )
        return False, True, text
    if text.startswith("/"):
        print(f"Unknown command: {text}")
        print("Type /help to see available commands.")
        return False, False, text

    for event in terminal_voice.build_events(text, now=now):
        rio.process_event(event)
    return False, True, text


def stdin_ready() -> bool:
    readable, _, _ = select.select([sys.stdin], [], [], 0.0)
    return bool(readable)


def build_orchestrator(*, use_real_services: bool) -> RioOrchestrator:
    rio = RioOrchestrator()
    if not use_real_services:
        configure_mock_services(rio)
    return rio


def main() -> int:
    parser = argparse.ArgumentParser(description="Live-test RIO state changes via webcam + terminal strings")
    parser.add_argument("--fps", type=float, default=8.0, help="webcam loop refresh rate")
    parser.add_argument("--away-timeout-ms", type=int, default=3000, help="time until Away transition after face lost")
    parser.add_argument("--engaged-idle-ms", type=int, default=1500, help="Engaged -> Idle timeout without interaction")
    parser.add_argument("--sleepy-ms", type=int, default=15000, help="Idle -> Sleepy timeout")
    parser.add_argument("--no-preview", action="store_true", help="disable preview window")
    parser.add_argument("--debug", action="store_true", help="debug mode showing webcam inset and state sidebar")
    parser.add_argument(
        "--real-services",
        action="store_true",
        help="use real weather/home_client handlers instead of mocks",
    )
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
        terminal_voice = TerminalVoiceInput(IntentNormalizer())
        rio = build_orchestrator(use_real_services=args.real_services)
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
        print("Make sure `.venv/bin/python -m pip install mediapipe opencv-python` is done first.")
        return 1

    had_face = False
    last_gesture: str | None = None
    last_input: str | None = None
    last_signature: tuple[str, ...] | None = None
    frame_interval = 1.0 / max(args.fps, 1.0)
    preview_enabled = not args.no_preview
    service_mode = "real-http" if args.real_services else "mock"

    print_help()
    ensure_initial_frame(rio)
    print_snapshot(
        rio,
        last_gesture=last_gesture,
        last_input=last_input,
        service_mode=service_mode,
        reason="initial",
    )

    try:
        while True:
            had_face, detected_gesture, camera_frame, face_event = process_frame(
                rio,
                stream,
                face_detector,
                face_tracker,
                gesture_detector,
                had_face=had_face,
            )
            if detected_gesture is not None:
                last_gesture = detected_gesture

            if preview_enabled:
                try:
                    should_exit_preview = show_preview(
                        camera_frame,
                        rio,
                        face_event=face_event,
                        last_gesture=last_gesture,
                        last_input=last_input,
                        service_mode=service_mode,
                        debug=args.debug,
                    )
                except Exception as exc:
                    preview_enabled = False
                    print(f"Disabling preview window: {exc}")
                else:
                    if should_exit_preview:
                        print("Exit requested from preview window.")
                        return 0

            force_print = False
            if stdin_ready():
                line = sys.stdin.readline()
                should_exit, force_print, user_input = process_console_line(rio, terminal_voice, line)
                if user_input is not None:
                    last_input = user_input
                if should_exit:
                    print("Exiting.")
                    return 0

            current_signature = snapshot_signature(rio, last_gesture, service_mode=service_mode)
            if force_print or current_signature != last_signature:
                reason = "console" if force_print else "state_changed"
                print_snapshot(
                    rio,
                    last_gesture=last_gesture,
                    last_input=last_input,
                    service_mode=service_mode,
                    reason=reason,
                )
                last_signature = current_signature

            time.sleep(frame_interval)
    except KeyboardInterrupt:
        print("\nExiting.")
        return 0
    finally:
        if preview_enabled:
            try:
                import cv2

                cv2.destroyAllWindows()
            except Exception:
                pass
        stream.close()


if __name__ == "__main__":
    raise SystemExit(main())
