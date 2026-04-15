#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.core.state.models import ActionKind, ContextState
from src.app.main import RioOrchestrator


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


@dataclass(frozen=True, slots=True)
class Scenario:
    key: str
    name: str
    description: str


SCENARIOS: list[Scenario] = [
    Scenario("1", "startled", "얼굴 없이 음성을 먼저 감지했을 때의 놀람 반응"),
    Scenario("2", "happy", "쓰다듬기 입력에 대한 기쁨 반응"),
    Scenario("3", "confused", "의도 해석 실패 시의 confused 반응"),
    Scenario("4", "welcome", "오래 자리를 비웠다가 돌아왔을 때의 반김 반응"),
    Scenario("5", "photo", "사진 찍기 시퀀스"),
    Scenario("6", "smarthome", "스마트홈 성공 피드백"),
    Scenario("7", "weather_fail", "날씨 조회 실패 피드백"),
]


def _fake_weather_failure(request):
    from src.app.domains.behavior.executor_registry import ExecutionResult

    return ExecutionResult(
        events=[
            Event.create(
                topics.TASK_STARTED,
                "demo.weather",
                payload={"task_id": "weather-demo", "kind": ActionKind.WEATHER.value},
                trace_id=request.trace_id,
            ),
            Event.create(
                topics.WEATHER_RESULT,
                "demo.weather",
                payload={"ok": False, "message": "network error"},
                trace_id=request.trace_id,
            ),
            Event.create(
                topics.TASK_FAILED,
                "demo.weather",
                payload={"task_id": "weather-demo", "kind": ActionKind.WEATHER.value, "message": "network error"},
                trace_id=request.trace_id,
            ),
        ]
    )


def _fake_smarthome_success(request):
    from src.app.domains.behavior.executor_registry import ExecutionResult

    return ExecutionResult(
        events=[
            Event.create(
                topics.TASK_STARTED,
                "demo.smarthome",
                payload={"task_id": "smarthome-demo", "kind": ActionKind.SMARTHOME.value},
                trace_id=request.trace_id,
            ),
            Event.create(
                topics.SMARTHOME_RESULT,
                "demo.smarthome",
                payload={"ok": True, "message": "거실 조명을 켰어."},
                trace_id=request.trace_id,
            ),
            Event.create(
                topics.TASK_SUCCEEDED,
                "demo.smarthome",
                payload={"task_id": "smarthome-demo", "kind": ActionKind.SMARTHOME.value},
                trace_id=request.trace_id,
            ),
        ]
    )


def build_orchestrator() -> RioOrchestrator:
    rio = RioOrchestrator()
    rio.registry.register(ActionKind.WEATHER, _fake_weather_failure)
    rio.registry.register(ActionKind.SMARTHOME, _fake_smarthome_success)
    return rio


def run_scenario(name: str) -> RioOrchestrator:
    rio = build_orchestrator()
    now = datetime.now(timezone.utc)

    if name == "startled":
        rio.process_event(Event.create(topics.VOICE_ACTIVITY_STARTED, "demo", timestamp=now))
    elif name == "happy":
        rio.process_event(Event.create(topics.TOUCH_STROKE_DETECTED, "demo", timestamp=now))
    elif name == "confused":
        rio.process_event(Event.create(topics.VOICE_INTENT_UNKNOWN, "demo", timestamp=now))
    elif name == "welcome":
        def seed_away(state):
            state.context_state = ContextState.AWAY
            state.extended.away_started_at = now - timedelta(seconds=5)
            state.extended.previous_context_state = ContextState.AWAY

        rio.store.mutate(seed_away)
        rio.process_event(
            Event.create(
                topics.VISION_FACE_DETECTED,
                "demo",
                payload={"center": (0.5, 0.5)},
                timestamp=now,
            )
        )
    elif name == "photo":
        rio.process_event(
            Event.create(
                topics.VISION_FACE_DETECTED,
                "demo",
                payload={"center": (0.5, 0.5)},
                timestamp=now,
            )
        )
        rio.process_event(Event.create(topics.VOICE_ACTIVITY_STARTED, "demo", timestamp=now))
        rio.process_event(
            Event.create(
                topics.VOICE_INTENT_DETECTED,
                "demo",
                payload={"intent": "camera.capture", "text": "사진 찍어줘"},
                timestamp=now,
            )
        )
    elif name == "smarthome":
        rio.process_event(
            Event.create(
                topics.VISION_FACE_DETECTED,
                "demo",
                payload={"center": (0.5, 0.5)},
                timestamp=now,
            )
        )
        rio.process_event(Event.create(topics.VOICE_ACTIVITY_STARTED, "demo", timestamp=now))
        rio.process_event(
            Event.create(
                topics.VOICE_INTENT_DETECTED,
                "demo",
                payload={"intent": "smarthome.light.on", "text": "불 켜줘"},
                timestamp=now,
            )
        )
    elif name == "weather_fail":
        rio.process_event(
            Event.create(
                topics.VISION_FACE_DETECTED,
                "demo",
                payload={"center": (0.5, 0.5)},
                timestamp=now,
            )
        )
        rio.process_event(Event.create(topics.VOICE_ACTIVITY_STARTED, "demo", timestamp=now))
        rio.process_event(
            Event.create(
                topics.VOICE_INTENT_DETECTED,
                "demo",
                payload={"intent": "weather.current", "text": "날씨 알려줘"},
                timestamp=now,
            )
        )
    else:
        raise KeyError(f"Unknown scenario: {name}")

    return rio


def render_terminal(rio: RioOrchestrator, *, title: str, description: str) -> None:
    state = rio.store.snapshot()
    frame = rio.renderer.history[-1] if rio.renderer.history else None
    if frame is None:
        print("아직 렌더된 프레임이 없습니다.")
        return

    mood = frame.face.mood
    style = MOOD_STYLES.get(mood, "")
    color_bar = f"{style}{' ' * 72}{RESET}"
    last_tts = rio.tts.history[-1] if rio.tts.history else "-"
    last_sfx = rio.sfx.history[-1] if rio.sfx.history else "-"

    print(CLEAR, end="")
    print(f"RIO Reaction Demo - {title}")
    print(description)
    print()
    for _ in range(8):
        print(color_bar)
    print()
    print(f"mood      : {mood}")
    print(f"ui        : {frame.ui}")
    print(f"overlay   : {frame.overlay.name}")
    print(f"hud       : {frame.hud.message}")
    print(f"context   : {state.context_state.value}")
    print(f"activity  : {state.activity_state.value}")
    print(f"oneshot   : {state.active_oneshot.name.value if state.active_oneshot else None}")
    print(f"tts       : {last_tts}")
    print(f"sfx       : {last_sfx}")
    print(f"events    : {len(rio.event_log)}")
    print()
    print("색상 해석:")
    print("  노랑=startled, 초록=happy/welcome, 회색=confused, 청록=attentive, 파랑=calm")
    print()


def interactive_loop(delay: float) -> int:
    scenarios_by_key = {item.key: item for item in SCENARIOS}
    scenarios_by_name = {item.name: item for item in SCENARIOS}

    while True:
        print(CLEAR, end="")
        print("RIO Reaction Demo")
        print("번호를 입력하면 해당 시나리오를 재생합니다.")
        print()
        for item in SCENARIOS:
            print(f"  {item.key}. {item.name:<12} - {item.description}")
        print()
        print("  a. 전체 자동 재생")
        print("  q. 종료")
        print()
        choice = input("> ").strip().lower()
        if choice == "q":
            return 0
        if choice == "a":
            autoplay(delay)
            continue

        scenario = scenarios_by_key.get(choice) or scenarios_by_name.get(choice)
        if scenario is None:
            print("알 수 없는 선택입니다.")
            time.sleep(1.0)
            continue

        rio = run_scenario(scenario.name)
        render_terminal(rio, title=scenario.name, description=scenario.description)
        input("엔터를 누르면 메뉴로 돌아갑니다...")


def autoplay(delay: float) -> None:
    for scenario in SCENARIOS:
        rio = run_scenario(scenario.name)
        render_terminal(rio, title=scenario.name, description=scenario.description)
        time.sleep(delay)


def main() -> int:
    parser = argparse.ArgumentParser(description="RIO 반응 상태를 터미널 색상으로 빠르게 확인하는 데모")
    parser.add_argument(
        "--scenario",
        choices=[item.name for item in SCENARIOS],
        help="하나의 시나리오만 실행하고 종료",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="모든 시나리오를 자동으로 순서대로 재생",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="자동 재생 시 각 시나리오 사이 대기 시간(초)",
    )
    args = parser.parse_args()

    if args.scenario:
        scenario = next(item for item in SCENARIOS if item.name == args.scenario)
        rio = run_scenario(scenario.name)
        render_terminal(rio, title=scenario.name, description=scenario.description)
        return 0

    if args.auto:
        autoplay(args.delay)
        return 0

    return interactive_loop(args.delay)


if __name__ == "__main__":
    raise SystemExit(main())
