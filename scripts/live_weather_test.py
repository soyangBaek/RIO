#!/usr/bin/env python3
"""live_weather_test.py — 날씨 기능 단독 테스트 (터미널 텍스트 입력).

음성 인식이나 카메라 없이 stdin 으로 명령어를 입력해서 weather 파이프라인을
빠르게 검증하고, 선택적으로 프리뷰 창에서 아이콘 오버레이까지 확인한다.

Usage:
    python scripts/live_weather_test.py                # 기본 (Open-Meteo 실 호출)
    python scripts/live_weather_test.py --preview      # 프리뷰 창에서 아이콘도 확인
    python scripts/live_weather_test.py --fullscreen   # 프리뷰를 풀스크린으로

Commands (프롬프트):
    w | weather              → weather.current intent 발행 (기본 위치 = seoul)
    w busan | weather busan  → 특정 위치 (devices.yaml 의 locations 키)
    mock sunny               → Open-Meteo 호출 건너뛰고 아이콘만 시각 확인
    mock cloudy|rainy|snowy|thunder|fog|unknown
    fail                     → 실패 결과를 시뮬레이션 (weather_failed SFX + confused oneshot)
    s | status               → 현재 orchestrator 상태 덤프
    h | help                 → 도움말
    q | quit | exit          → 종료
"""
from __future__ import annotations

import argparse
import select
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _inject_local_venv_site_packages() -> None:
    venv_lib = REPO_ROOT / ".venv" / "lib"
    if not venv_lib.exists():
        return
    for site_packages in venv_lib.glob("python*/site-packages"):
        if str(site_packages) not in sys.path:
            sys.path.insert(0, str(site_packages))


_inject_local_venv_site_packages()

from src.app.core.events import topics  # noqa: E402
from src.app.core.events.models import Event  # noqa: E402
from src.app.core.state.models import ActionKind  # noqa: E402
from src.app.core.state.scene_selector import select_scene  # noqa: E402
from src.app.main import RioOrchestrator  # noqa: E402


MOCK_ICON_KEYS = {"sunny", "cloudy", "rainy", "snowy", "thunder", "fog", "unknown"}

_MOCK_CONDITION = {
    "sunny": "clear",
    "cloudy": "overcast",
    "rainy": "rain",
    "snowy": "snow",
    "thunder": "thunderstorm",
    "fog": "fog",
    "unknown": "unknown",
}

HELP_TEXT = """
Commands:
  w | weather [location]   — fire weather.current intent (optionally 'busan' / 'incheon')
  mock <icon>              — skip HTTP and push a fake success result
                              <icon> one of: sunny, cloudy, rainy, snowy, thunder, fog, unknown
  fail                     — push a failure result
  s | status               — print orchestrator weather state
  h | help                 — show this help
  q | quit | exit          — leave
""".strip()


def _ts() -> str:
    t = time.time()
    return time.strftime("%H:%M:%S", time.localtime(t)) + f".{int((t - int(t)) * 1000):03d}"


def _ensure_initial_frame(rio: RioOrchestrator) -> None:
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


def _stdin_ready() -> bool:
    readable, _, _ = select.select([sys.stdin], [], [], 0.0)
    return bool(readable)


def _print_status(rio: RioOrchestrator) -> None:
    end_at = rio.weather_display_end_at
    if end_at is None:
        remaining = "-"
    else:
        delta = (end_at - datetime.now(timezone.utc)).total_seconds()
        remaining = f"{max(0.0, delta):.2f}s"
    snapshot = rio.store.snapshot()
    print(f"[{_ts()}] status:")
    print(f"  context     : {snapshot.context_state.value}")
    print(f"  activity    : {snapshot.activity_state.value}")
    print(f"  icon_key    : {rio.weather_icon_key}")
    print(f"  display left: {remaining}")
    print(f"  last SFX    : {rio.sfx.history[-1] if rio.sfx.history else '-'}")


def _print_event_trace(events: list[Event]) -> None:
    for ev in events:
        if ev.topic == topics.WEATHER_RESULT:
            payload = ev.payload
            ok = payload.get("ok")
            tag = "OK " if ok else "ERR"
            print(
                f"[{_ts()}] WEATHER_RESULT {tag} "
                f"condition={payload.get('condition')!s:>12} "
                f"icon={payload.get('icon_key')!s:>8} "
                f"temp={payload.get('temperature_c')}°C "
                f"msg={payload.get('message', '')}"
            )
        elif ev.topic == topics.TASK_STARTED and ev.payload.get("kind") == ActionKind.WEATHER.value:
            print(f"[{_ts()}] TASK_STARTED (weather)")
        elif ev.topic in {topics.TASK_SUCCEEDED, topics.TASK_FAILED} and ev.payload.get("kind") == ActionKind.WEATHER.value:
            print(f"[{_ts()}] {ev.topic} (weather) msg={ev.payload.get('message', '')}")


def _emit_real_intent(rio: RioOrchestrator, location: str | None) -> list[Event]:
    # 실제 handler 경로를 타기 위해 Listening 상태를 만들어준다.
    rio.process_event(Event.create(topics.VISION_FACE_DETECTED, "live_weather", payload={"center": (0.5, 0.5)}))
    rio.process_event(Event.create(topics.VOICE_ACTIVITY_STARTED, "live_weather"))
    payload: dict[str, object] = {"intent": "weather.current", "text": "(terminal test)"}
    if location:
        payload["location"] = location
    processed = rio.process_event(
        Event.create(topics.VOICE_INTENT_DETECTED, "live_weather", payload=payload)
    )
    # handler 가 background 큐에 실행 결과를 넣을 수 있으므로 잠깐 drain.
    deadline = time.time() + 2.0
    while time.time() < deadline:
        rio.pump_workers()
        batch = rio.drain_bus()
        processed.extend(batch)
        if any(
            ev.topic in {topics.TASK_SUCCEEDED, topics.TASK_FAILED}
            and ev.payload.get("kind") == ActionKind.WEATHER.value
            for ev in processed
        ):
            break
        time.sleep(0.02)
    return processed


def _emit_mock_success(rio: RioOrchestrator, icon_key: str) -> list[Event]:
    payload = {
        "ok": True,
        "condition": _MOCK_CONDITION.get(icon_key, icon_key),
        "temperature_c": 21.3,
        "icon_key": icon_key,
        "raw": {"mocked": True},
    }
    events: list[Event] = []
    events.extend(rio.process_event(Event.create(topics.TASK_STARTED, "live_weather.mock", payload={"task_id": "mock", "kind": ActionKind.WEATHER.value})))
    events.extend(rio.process_event(Event.create(topics.WEATHER_RESULT, "live_weather.mock", payload=payload)))
    events.extend(rio.process_event(Event.create(topics.TASK_SUCCEEDED, "live_weather.mock", payload={"task_id": "mock", "kind": ActionKind.WEATHER.value, "message": "mock ok"})))

    # main.py 의 handler factory 가 해주는 orchestrator 상태 세팅을 mock 경로에서도 흉내낸다.
    from datetime import timedelta

    from src.app.main import WEATHER_DISPLAY_DURATION_SECONDS
    rio.weather_display_end_at = datetime.now(timezone.utc) + timedelta(seconds=WEATHER_DISPLAY_DURATION_SECONDS)
    rio.weather_icon_key = icon_key
    return events


def _emit_mock_failure(rio: RioOrchestrator) -> list[Event]:
    payload = {"ok": False, "message": "simulated failure"}
    events: list[Event] = []
    events.extend(rio.process_event(Event.create(topics.TASK_STARTED, "live_weather.mock", payload={"task_id": "mock", "kind": ActionKind.WEATHER.value})))
    events.extend(rio.process_event(Event.create(topics.WEATHER_RESULT, "live_weather.mock", payload=payload)))
    events.extend(rio.process_event(Event.create(topics.TASK_FAILED, "live_weather.mock", payload={"task_id": "mock", "kind": ActionKind.WEATHER.value, "message": "simulated failure"})))
    return events


def _handle_line(rio: RioOrchestrator, line: str) -> bool:
    """Return False to signal exit."""
    stripped = line.strip()
    if not stripped:
        return True
    parts = stripped.split()
    cmd = parts[0].lower()

    if cmd in {"q", "quit", "exit"}:
        return False
    if cmd in {"h", "help", "?"}:
        print(HELP_TEXT)
        return True
    if cmd in {"s", "status"}:
        _print_status(rio)
        return True
    if cmd in {"w", "weather"}:
        location = parts[1] if len(parts) >= 2 else None
        if location:
            print(f"[{_ts()}] → weather.current (location={location})")
        else:
            print(f"[{_ts()}] → weather.current (default location)")
        _print_event_trace(_emit_real_intent(rio, location))
        _print_status(rio)
        return True
    if cmd == "mock":
        icon = parts[1].lower() if len(parts) >= 2 else ""
        if icon not in MOCK_ICON_KEYS:
            print(f"  unknown icon {icon!r}. expected one of: {sorted(MOCK_ICON_KEYS)}")
            return True
        print(f"[{_ts()}] → mock success icon={icon}")
        _print_event_trace(_emit_mock_success(rio, icon))
        _print_status(rio)
        return True
    if cmd == "fail":
        print(f"[{_ts()}] → mock failure")
        _print_event_trace(_emit_mock_failure(rio))
        _print_status(rio)
        return True

    print(f"  unknown command {cmd!r}. type 'help' for usage.")
    return True


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Live weather pipeline test via terminal text input.")
    parser.add_argument("--preview", action="store_true", help="open PreviewWindow to see the icon overlay")
    parser.add_argument("--fullscreen", action="store_true", help="open preview fullscreen")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    rio = RioOrchestrator()
    # 터미널 전용이라 voice backend 는 항상 끈다.
    rio.voice_backend = None

    preview = None
    if args.preview:
        from src.app.adapters.display.preview_window import PreviewWindow
        preview = PreviewWindow(fullscreen=args.fullscreen)

    print("RIO live weather test — type 'help' for commands, 'q' to quit.")
    print("Default location = 'seoul' (see configs/devices.yaml to add more).")
    print()

    with rio:
        if preview is not None:
            _ensure_initial_frame(rio)
        print("> ", end="", flush=True)
        try:
            while True:
                rio.pump_workers()
                rio.drain_bus()

                if _stdin_ready():
                    line = sys.stdin.readline()
                    if not line:
                        break
                    if not _handle_line(rio, line):
                        break
                    print("> ", end="", flush=True)

                quit_requested = False
                if preview is not None:
                    quit_requested = preview.update(rio)
                if quit_requested:
                    print("\npreview window requested quit")
                    break
                time.sleep(0.02)
        except (KeyboardInterrupt, EOFError):
            print("\nexiting")
        finally:
            if preview is not None:
                preview.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
