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
from src.app.core.safety.startup_report import print_startup_report  # noqa: E402
from src.app.core.safety.tick_metrics import TickMetrics, set_active_metrics  # noqa: E402
from src.app.core.state.scene_selector import select_scene  # noqa: E402
from src.app.main import RioOrchestrator  # noqa: E402


_LOGGER = logging.getLogger("rio.app")

_BUILTIN_DEFAULTS: dict[str, object] = {
    "preview": False,
    "fullscreen": True,
    "tick_hz": 30.0,
    "log_level": "INFO",
    "no_voice": False,
    "metrics_interval_s": 5.0,
}


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
        "--metrics-interval",
        type=float,
        default=None,
        help="Rolling tick metrics summary interval in seconds (0 disables).",
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
    # CLI → profile 역방향 매핑. voice 플래그는 저장 시 no_voice 로 반전.
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
    if args.metrics_interval is not None:
        cli_overrides["metrics_interval_s"] = args.metrics_interval
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

    metrics_interval = float(cfg["metrics_interval_s"])
    metrics = TickMetrics(interval_s=metrics_interval)
    # adapter (face/gesture/vision_worker/live_voice_backend) 가 공유 metrics 에
    # 자기 지표를 기록할 수 있도록 프로세스 전역 accessor 를 세팅한다.
    set_active_metrics(metrics)

    with rio:
        print_startup_report(rio, no_voice=bool(cfg["no_voice"]))
        if preview is not None:
            _ensure_initial_frame(rio)

        cycles = 0
        try:
            while True:
                t0 = time.monotonic()
                rio.pump_workers()
                t1 = time.monotonic()
                rio.drain_bus()
                t2 = time.monotonic()
                metrics.record("pump_ms", (t1 - t0) * 1000.0)
                metrics.record("drain_ms", (t2 - t1) * 1000.0)

                quit_requested = False
                if preview is not None:
                    quit_requested = preview.update(rio)
                    metrics.record("preview_ms", (time.monotonic() - t2) * 1000.0)

                metrics.tick_done()
                metrics.maybe_log()

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
            if metrics.total_ticks > 0:
                _LOGGER.info("[metrics final] %s", metrics.format_summary())
            set_active_metrics(None)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
