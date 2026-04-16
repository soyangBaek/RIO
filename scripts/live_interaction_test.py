#!/usr/bin/env python3
from __future__ import annotations

import argparse
import select
import sys
import time
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
    print("웹캠은 실시간으로 얼굴/손 제스처를 읽고, 음성은 터미널 문자열로 흉내냅니다.")
    print("별도 웹캠 프리뷰 창에 현재 상태와 감지 결과를 함께 표시합니다.")
    print("기본값은 mock 서비스이며, 실제 HTTP 요청 확인은 --real-services 로 실행합니다.")
    print()
    print("터미널 입력 예시:")
    print("  사진 찍어줘")
    print("  날씨 알려줘")
    print("  불 켜줘")
    print("  게임 모드로 바꿔줘")
    print("  취소")
    print("  확인")
    print()
    print("보조 명령:")
    print("  /tap           - 터치 탭 이벤트")
    print("  /stroke        - 쓰다듬기 이벤트")
    print("  /gesture NAME  - vision gesture 시뮬레이션 (wave, finger_gun, v_sign, head_left, head_right, peekaboo)")
    print("  /face left|center|right|lost - 얼굴 위치/손실 시뮬레이션")
    print("  /timer [label] - 타이머 만료 이벤트")
    print("  /status        - 현재 상태 출력")
    print("  /help          - 도움말")
    print("  /quit          - 종료")
    print()
    print("웹캠 테스트 팁:")
    print("  얼굴만 보이면 Away -> Idle")
    print("  얼굴을 보인 상태에서 open_palm 손 모양을 보이면 Idle -> Engaged")
    print("  v_sign은 camera.capture로 매핑되어 사진 시퀀스를 실행")
    print("  프리뷰 창에서 q 또는 ESC를 누르면 종료")


def preview_center_to_pixels(frame: Any, center: tuple[float, float] | None) -> tuple[int, int] | None:
    if center is None or not hasattr(frame, "shape"):
        return None
    height, width = frame.shape[:2]
    x = int(max(0.0, min(1.0, center[0])) * width)
    y = int(max(0.0, min(1.0, center[1])) * height)
    return x, y


def show_preview(
    frame: Any,
    rio: RioOrchestrator,
    *,
    face_event: Event | None,
    last_gesture: str | None,
    last_input: str | None,
    service_mode: str,
) -> bool:
    if not hasattr(frame, "copy"):
        return False

    import cv2

    preview = frame.copy()
    snapshot = rio.store.snapshot()
    render_frame = rio.renderer.history[-1] if rio.renderer.history else None
    details = describe_runtime_snapshot(rio, service_mode=service_mode)
    lines = [
        f"context: {snapshot.context_state.value}",
        f"activity: {snapshot.activity_state.value}",
        f"mood: {render_frame.face.mood if render_frame else '-'}",
        f"ui: {render_frame.ui if render_frame else '-'}",
        f"doing: {trim_text(details['current_action'], limit=46)}",
        f"intent: {trim_text(details['last_intent'], limit=45)}",
        f"result: {trim_text(details['last_result'], limit=45)}",
        f"mode: {details['service_mode']} / {details['http_transport']}",
        f"http: {details['http_sent']} ({details['http_status']})",
        f"target: {trim_text(details['http_target'], limit=44)}",
        f"payload: {trim_text(details['http_payload'], limit=43)}",
        f"gesture: {last_gesture or '-'}",
        f"last input: {trim_text(last_input, limit=42)}",
        f"hud: {(render_frame.hud.message if render_frame else '-') or '-'}",
    ]

    cv2.rectangle(preview, (12, 12), (580, 314), (0, 0, 0), -1)
    cv2.rectangle(preview, (12, 12), (580, 314), (60, 220, 180), 2)
    for idx, line in enumerate(lines):
        cv2.putText(
            preview,
            line,
            (24, 38 + idx * 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            (240, 240, 240),
            1,
            cv2.LINE_AA,
        )

    if face_event is not None:
        center = preview_center_to_pixels(preview, tuple(face_event.payload.get("center", (0.5, 0.5))))
        if center is not None:
            cv2.circle(preview, center, 12, (0, 255, 0), 2)
            cv2.putText(
                preview,
                "face",
                (center[0] + 14, max(30, center[1] - 14)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 0),
                1,
                cv2.LINE_AA,
            )

    if last_gesture:
        cv2.putText(
            preview,
            f"gesture: {last_gesture}",
            (24, max(220, preview.shape[0] - 24)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (80, 255, 255),
            2,
            cv2.LINE_AA,
        )

    cv2.imshow("RIO Live Camera", preview)
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
            print("예: /gesture wave")
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
            print("예: /face left | /face center | /face right | /face lost")
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
        print(f"알 수 없는 명령: {text}")
        print("/help 를 입력하면 사용 가능한 명령을 볼 수 있습니다.")
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
    parser = argparse.ArgumentParser(description="웹캠 + 터미널 문자열로 RIO 상태 변화를 라이브 테스트")
    parser.add_argument("--fps", type=float, default=8.0, help="웹캠 루프 갱신 주기")
    parser.add_argument("--away-timeout-ms", type=int, default=3000, help="얼굴 미검출 후 Away 전이까지의 시간")
    parser.add_argument("--engaged-idle-ms", type=int, default=1500, help="상호작용이 없을 때 Engaged -> Idle 시간")
    parser.add_argument("--sleepy-ms", type=int, default=15000, help="Idle -> Sleepy 시간")
    parser.add_argument("--no-preview", action="store_true", help="웹캠 프리뷰 창을 띄우지 않음")
    parser.add_argument(
        "--real-services",
        action="store_true",
        help="mock 대신 실제 weather/home_client 핸들러 사용",
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
        print(f"초기화 실패: {exc}")
        print("먼저 `.venv/bin/python -m pip install mediapipe opencv-python` 가 완료됐는지 확인하세요.")
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
                    )
                except Exception as exc:
                    preview_enabled = False
                    print(f"프리뷰 창을 비활성화합니다: {exc}")
                else:
                    if should_exit_preview:
                        print("프리뷰 창에서 종료 요청을 받아 종료합니다.")
                        return 0

            force_print = False
            if stdin_ready():
                line = sys.stdin.readline()
                should_exit, force_print, user_input = process_console_line(rio, terminal_voice, line)
                if user_input is not None:
                    last_input = user_input
                if should_exit:
                    print("종료합니다.")
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
        print("\n종료합니다.")
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
