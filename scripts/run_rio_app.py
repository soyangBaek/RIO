#!/usr/bin/env python3
"""RIO 실제 앱 진입점.

live_interaction_test.py / live_voice_interaction_test.py 는 카메라 프리뷰,
콘솔 명령, voice trace 등 테스트 하네스 기능이 많이 섞여 있어 실제 앱 실행
경로로 쓰기 어렵다. 이 스크립트는 RioOrchestrator 하나만 들고 돌아가는
최소 진입점이다 — 상세 trace 가 필요한 사람은 기존 live_* 스크립트를 계속 쓴다.

--profile <name> 을 주면 configs/runtime_<name>.yaml 로부터 기본값을 읽는다.
CLI 플래그가 있으면 프로파일 값을 덮어쓴다. --preview / --no-preview 처럼
명시적으로 반대 값을 지정할 수도 있다.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
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

import yaml  # noqa: E402

from src.app.core.config import resolve_repo_path  # noqa: E402
from src.app.core.events import topics  # noqa: E402
from src.app.core.events.models import Event  # noqa: E402
from src.app.core.safety.startup_report import print_startup_report  # noqa: E402
from src.app.core.state.scene_selector import select_scene  # noqa: E402
from src.app.main import RioOrchestrator  # noqa: E402


_LOGGER = logging.getLogger("rio.app")

_BUILTIN_DEFAULTS: dict[str, object] = {
    "preview": False,
    "fullscreen": True,
    "tick_hz": 30.0,
    "log_level": "INFO",
    "no_voice": False,
    "trace_events": False,
}


_SEPARATOR = "─" * 72


def _ts() -> str:
    t = time.time()
    return time.strftime("%H:%M:%S", time.localtime(t)) + f".{int((t - int(t)) * 1000):03d}"


def _print_separator(label: str | None = None) -> None:
    """Print a visual separator line. If label is given, embed it in the middle."""
    if label is None:
        print(_SEPARATOR, flush=True)
        return
    body = f"── {label} "
    fill = max(4, 72 - len(body))
    print(f"{body}{'─' * fill}", flush=True)


def _print_state_change(event: Event) -> None:
    """Highlight FSM state changes with dashed separator, always on."""
    if event.topic == topics.CONTEXT_STATE_CHANGED:
        _print_separator(
            f"[{_ts()}] context: {event.payload.get('from')} → {event.payload.get('to')}"
        )
    elif event.topic == topics.ACTIVITY_STATE_CHANGED:
        kind = event.payload.get("kind")
        suffix = f" ({kind})" if kind else ""
        _print_separator(
            f"[{_ts()}] activity: {event.payload.get('from')} → "
            f"{event.payload.get('to')}{suffix}"
        )


def _print_voice_intent(event: Event) -> None:
    """live_voice_interaction_test 스타일: 음성 인식 직후 text/intent/confidence 블록."""
    payload = event.payload
    text = payload.get("text") or ""
    normalized = payload.get("normalized_text") or text
    intent = payload.get("intent") or "-"
    conf = event.confidence if event.confidence is not None else 0.0
    _print_separator(f"[{_ts()}] voice heard")
    print(f"  text       : {text}", flush=True)
    if normalized and normalized != text:
        print(f"  normalized : {normalized}", flush=True)
    print(f"  intent     : {intent}", flush=True)
    print(f"  confidence : {conf:.2f}", flush=True)
    _print_separator()


def _print_voice_unknown(event: Event) -> None:
    payload = event.payload
    text = payload.get("text") or ""
    reason = payload.get("reason") or "-"
    _print_separator(f"[{_ts()}] voice UNKNOWN")
    print(f"  text       : {text}", flush=True)
    print(f"  reason     : {reason}", flush=True)
    _print_separator()


def _format_event_trace(event: Event) -> str | None:
    """Return a human-readable one-liner for interesting events, or None to skip.

    State changes and voice intents 는 별도 함수가 더 눈에 띄게 출력하므로 여기서는 None.
    """
    topic = event.topic
    payload = event.payload
    if topic == topics.VISION_GESTURE_DETECTED:
        return f"gesture={payload.get('gesture')} conf={payload.get('confidence', 0.0):.2f}"
    if topic == topics.VISION_FACE_DETECTED:
        center = payload.get("center")
        return f"face detected center={center} conf={payload.get('confidence', 0.0):.2f}"
    if topic == topics.VISION_FACE_LOST:
        return "face lost"
    if topic == topics.VOICE_ACTIVITY_STARTED:
        return "voice activity START"
    if topic == topics.VOICE_ACTIVITY_ENDED:
        return "voice activity END"
    if topic == topics.TASK_STARTED:
        return f"task STARTED kind={payload.get('kind')} id={payload.get('task_id')}"
    if topic == topics.TASK_SUCCEEDED:
        return f"task OK kind={payload.get('kind')}"
    if topic == topics.TASK_FAILED:
        return f"task FAILED kind={payload.get('kind')} msg={payload.get('message')}"
    if topic == topics.ONESHOT_TRIGGERED:
        return f"oneshot {payload.get('name')}"
    if topic == topics.TIMER_EXPIRED:
        return f"timer expired label={payload.get('label')}"
    if topic == topics.SMARTHOME_RESULT:
        ok = payload.get("ok")
        return f"smarthome result ok={ok} msg={payload.get('message')}"
    return None


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RIO application entry point (production-ish)."
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Load configs/runtime_<profile>.yaml for defaults (e.g. 'app' or 'live_test').",
    )
    # 명시적으로 지정되지 않은 플래그는 None 으로 두고, 프로파일/빌트인 기본값으로 채운다.
    parser.add_argument(
        "--tick-hz",
        type=float,
        default=None,
        help="Event loop tick rate in Hz.",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=0,
        help="Stop after N ticks. 0 = run forever (default).",
    )
    parser.add_argument(
        "--voice",
        dest="voice",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable/disable voice backend (default from profile or true).",
    )
    parser.add_argument(
        "--preview",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Open/skip OpenCV face preview window. ESC or q to quit the window.",
    )
    parser.add_argument(
        "--fullscreen",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="When preview is on, fullscreen vs windowed.",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        help="Python logging level.",
    )
    parser.add_argument(
        "--trace-events",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Log per-tick gesture/task events one line each (verbose).",
    )
    return parser.parse_args(argv)


def _load_profile(name: str | None) -> dict[str, object]:
    if not name:
        return {}
    path = resolve_repo_path(f"configs/runtime_{name}.yaml")
    if not path.exists():
        _LOGGER.warning("profile '%s' not found (%s); using built-in defaults", name, path)
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        _LOGGER.warning("profile '%s' is not a mapping; ignoring", name)
        return {}
    return data


def _resolve_config(args: argparse.Namespace) -> dict[str, object]:
    profile = _load_profile(args.profile)
    resolved: dict[str, object] = dict(_BUILTIN_DEFAULTS)
    for key, value in profile.items():
        if key in resolved:
            resolved[key] = value
    cli_overrides: dict[str, object] = {}
    if args.tick_hz is not None:
        cli_overrides["tick_hz"] = args.tick_hz
    if args.preview is not None:
        cli_overrides["preview"] = args.preview
    if args.fullscreen is not None:
        cli_overrides["fullscreen"] = args.fullscreen
    if args.log_level is not None:
        cli_overrides["log_level"] = args.log_level
    if args.voice is not None:
        cli_overrides["no_voice"] = not args.voice
    if args.trace_events is not None:
        cli_overrides["trace_events"] = args.trace_events
    resolved.update(cli_overrides)
    return resolved


def _ensure_initial_frame(rio: RioOrchestrator) -> None:
    """렌더 히스토리가 비어 있으면 현재 스냅샷 기반으로 최초 프레임을 한 번 찍어둔다.
    PreviewWindow 는 렌더 히스토리가 비면 검은 화면만 보여주기 때문."""
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


def run(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    cfg = _resolve_config(args)

    logging.basicConfig(
        level=getattr(logging, str(cfg["log_level"]).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    if args.profile:
        _LOGGER.info("loaded profile '%s'", args.profile)

    rio = RioOrchestrator()
    if bool(cfg["no_voice"]) and rio.voice_backend is not None:
        rio.voice_backend = None

    tick_hz = max(float(cfg["tick_hz"]), 1.0)
    tick_sleep = 1.0 / tick_hz
    max_cycles = args.max_cycles if args.max_cycles > 0 else None

    preview = None
    if bool(cfg["preview"]):
        from src.app.adapters.display.preview_window import PreviewWindow
        preview = PreviewWindow(fullscreen=bool(cfg["fullscreen"]))

    trace_events = bool(cfg["trace_events"])
    event_logger = logging.getLogger("rio.event")

    # startup report 를 먼저 찍는다. RioOrchestrator.__enter__ 가 voice_backend.start()
    # 안에서 _ensure_whisper() 를 부르면 첫 실행 시 수십 MB 모델 다운로드 때문에 블로킹될 수
    # 있는데, 그 전에 헬스 체크는 사용자가 즉시 볼 수 있어야 한다.
    print_startup_report(rio, no_voice=bool(cfg["no_voice"]))

    with rio:
        if preview is not None:
            _ensure_initial_frame(rio)

        cycles = 0
        try:
            while True:
                rio.pump_workers()
                drained = rio.drain_bus()

                for ev in drained:
                    # 항상 출력: FSM 전이와 음성 인식 결과는 trace_events 와 무관하게 보여준다.
                    if ev.topic in {topics.CONTEXT_STATE_CHANGED, topics.ACTIVITY_STATE_CHANGED}:
                        _print_state_change(ev)
                    elif ev.topic == topics.VOICE_INTENT_DETECTED:
                        _print_voice_intent(ev)
                    elif ev.topic == topics.VOICE_INTENT_UNKNOWN:
                        _print_voice_unknown(ev)
                    elif trace_events:
                        line = _format_event_trace(ev)
                        if line is not None:
                            event_logger.info(line)

                quit_requested = False
                if preview is not None:
                    quit_requested = preview.update(rio)

                if quit_requested:
                    _LOGGER.info("preview window requested quit")
                    break
                cycles += 1
                if max_cycles is not None and cycles >= max_cycles:
                    break
                if preview is None:
                    time.sleep(tick_sleep)
                elif tick_sleep > 0.001:
                    # preview 가 켜진 경우 cv2.waitKey(1) 이 ~1ms sleep 역할을 해서
                    # 별도 sleep 은 줄여 쓴다.
                    time.sleep(max(0.0, tick_sleep - 0.001))
        except KeyboardInterrupt:
            _LOGGER.info("keyboard interrupt received, shutting down")
        finally:
            if preview is not None:
                preview.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
