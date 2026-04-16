"""T-058: 메인 오케스트레이터 진입점.

core/bus 초기화, worker 시작, 이벤트 루프 실행.
extended state → reducers → oneshot → scene selector → effect planner → executor registry.
"""
from __future__ import annotations

import logging
import signal
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from src.app.adapters.camera.capture import CameraCapture
from src.app.adapters.camera.storage import PhotoStorage
from src.app.adapters.display.renderer import DisplayRenderer
from src.app.adapters.home_client.client import HomeClient
from src.app.adapters.speaker.sfx import SfxPlayer
from src.app.adapters.speaker.tts import TtsAdapter
from src.app.adapters.touch.input import TouchInput
from src.app.adapters.weather.client import WeatherClient
from src.app.core.bus.queue_bus import QueueBus
from src.app.core.bus.router import EventRouter
from src.app.core.events.models import Event
from src.app.core.events.topics import Topics
from src.app.core.safety.capabilities import CapabilityManager
from src.app.core.safety.heartbeat_monitor import HeartbeatMonitor
from src.app.core.scheduler.timer_scheduler import TimerScheduler
from src.app.core.state.models import ActivityState, ExecutingKind
from src.app.core.state.reducers import ReducerResult, reduce
from src.app.core.state.store import Store
from src.app.domains.behavior.effect_planner import EffectPlanner
from src.app.domains.behavior.executor_registry import ExecutorRegistry
from src.app.domains.behavior.interrupts import InterruptPolicy
from src.app.domains.games.service import GameService
from src.app.domains.gesture.mapper import GestureActionMapper
from src.app.domains.photo.service import PhotoService
from src.app.domains.smart_home.service import SmartHomeService
from src.app.domains.speech.dedupe import IntentDedupe
from src.app.domains.timers.service import TimerService
from src.app.scenes.catalog import SceneCatalog
from src.app.workers.audio_worker import AudioWorker
from src.app.workers.vision_worker import VisionWorker

logger = logging.getLogger("rio")

LOOP_INTERVAL = 1 / 60  # ~60Hz main loop


def load_config(base_path: str = ".") -> Dict[str, Any]:
    """configs/ 디렉터리에서 설정 로드."""
    config: Dict[str, Any] = {}
    configs_dir = Path(base_path) / "configs"

    for name in ("robot", "thresholds", "triggers", "devices", "scenes"):
        path = configs_dir / f"{name}.yaml"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            config[name] = data
            # flatten thresholds into top-level for reducer access
            if name == "thresholds":
                config.update(data)
        else:
            config[name] = {}

    return config


class RioApp:
    """RIO 메인 애플리케이션."""

    def __init__(self, headless: bool = False, base_path: str = ".") -> None:
        self._headless = headless
        self._base_path = base_path
        self._running = False

        # config
        self._config = load_config(base_path)

        # core
        self._store = Store()
        self._audio_bus = QueueBus()
        self._vision_bus = QueueBus()
        self._router = EventRouter()
        self._scheduler = TimerScheduler()
        self._heartbeat = HeartbeatMonitor()
        self._capability_mgr = CapabilityManager(self._store)

        # display / speaker
        robot_cfg = self._config.get("robot", {})
        display_cfg = robot_cfg.get("display", {})
        self._display = DisplayRenderer(
            width=display_cfg.get("width", 480) or 480,
            height=display_cfg.get("height", 320) or 320,
            headless=headless,
        )
        self._sfx = SfxPlayer(base_path=base_path, headless=headless)
        self._tts = TtsAdapter(headless=headless)
        self._touch = TouchInput(headless=headless)

        # domains
        self._interrupt_policy = InterruptPolicy(self._store)
        self._effect_planner = EffectPlanner()
        self._executor = ExecutorRegistry()
        self._intent_dedupe = IntentDedupe(
            cooldown_ms=self._config.get("behavior", {}).get("intent_cooldown_ms", 1500)
        )
        self._gesture_mapper = GestureActionMapper()
        self._scene_catalog = SceneCatalog(self._config.get("scenes"))

        # adapters
        devices_cfg = self._config.get("devices", {})
        home_client_cfg = devices_cfg.get("home_client", {})
        self._home_client = HomeClient(
            base_url=home_client_cfg.get("base_url", "http://127.0.0.1"),
        )
        self._weather_client = WeatherClient()
        self._camera_capture = CameraCapture(headless=headless)
        self._photo_storage = PhotoStorage()

        # services
        self._photo_service = PhotoService(
            camera_capture=self._camera_capture, sfx_player=self._sfx
        )
        self._timer_service = TimerService(self._scheduler)
        self._smarthome_service = SmartHomeService(self._home_client)
        self._game_service = GameService()

        # register executors
        self._executor.register("photo", self._photo_service.handle)
        self._executor.register("timer_setup", self._timer_service.handle)
        self._executor.register("smarthome", self._smarthome_service.handle)
        self._executor.register("weather", self._handle_weather)
        self._executor.register("game", self._game_service.handle)
        self._executor.register("dance", self._game_service.handle)

        # workers
        self._audio_worker = AudioWorker(self._audio_bus, self._config, headless=headless)
        self._vision_worker = VisionWorker(self._vision_bus, self._config, headless=headless)

    def _handle_weather(self, payload: Dict[str, Any], done_callback) -> None:
        """Weather executor: 날씨 조회 + 결과 피드백."""
        import threading

        def _fetch():
            event = self._weather_client.fetch_weather()
            ok = event.payload.get("ok", False)
            if ok:
                data = event.payload.get("data", {})
                done_callback(True, result=data)
            else:
                done_callback(False, error=event.payload.get("error", ""))

        threading.Thread(target=_fetch, daemon=True).start()

    def initialize(self) -> None:
        """모든 컴포넌트 초기화."""
        self._display.initialize()
        self._sfx.initialize()
        self._tts.initialize()

        # 내부 이벤트 구독
        self._router.subscribe("*", self._on_internal_event)

        # heartbeat 등록
        self._heartbeat.register_worker("audio_worker")
        self._heartbeat.register_worker("vision_worker")

        logger.info("RIO initialized (headless=%s)", self._headless)

    def start(self) -> None:
        """워커 시작 + 메인 루프."""
        self._running = True

        # signal handler
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # workers
        self._audio_worker.start()
        self._vision_worker.start()

        logger.info("RIO started")

        try:
            self._main_loop()
        finally:
            self.shutdown()

    def _main_loop(self) -> None:
        """메인 이벤트 루프."""
        while self._running:
            loop_start = time.time()

            # 1. 워커 큐에서 이벤트 수신
            audio_events = self._audio_bus.drain()
            vision_events = self._vision_bus.drain()

            # 2. 터치 이벤트
            touch_events = self._touch.poll_events()

            # 3. 타이머 이벤트
            timer_events = self._scheduler.tick()

            # 4. heartbeat 체크
            degraded_events = self._heartbeat.check_timeouts()

            # 모든 이벤트 처리
            all_events = audio_events + vision_events + touch_events + timer_events + degraded_events

            for event in all_events:
                self._process_event(event)

            # display 렌더
            self._display.render()

            # 루프 간격 유지
            elapsed = time.time() - loop_start
            sleep_time = LOOP_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _process_event(self, event: Event) -> None:
        """이벤트 하나 처리: interrupt → reduce → effect → execute."""

        # heartbeat 처리
        self._heartbeat.handle_event(event)
        self._capability_mgr.handle_degraded(event)

        # gesture → intent 변환
        if event.topic == Topics.VISION_GESTURE_DETECTED:
            mapped = self._gesture_mapper.map_event(event)
            if mapped:
                event = mapped

        # intent dedupe
        if event.topic == Topics.VOICE_INTENT_DETECTED:
            intent = event.payload.get("intent", "")
            if self._intent_dedupe.is_duplicate(intent):
                return

        # interrupt policy
        filtered = self._interrupt_policy.apply(event)
        if filtered is None:
            return

        # eye tracking 업데이트
        if event.topic == Topics.VISION_FACE_MOVED:
            center = event.payload.get("center", [0.5, 0.5])
            self._display.update_eye_position(center[0], center[1])
        elif event.topic == Topics.VISION_FACE_LOST:
            self._display.on_face_lost()

        # reduce
        result = reduce(self._store, event, self._config)

        # process output events (router 내부 발행)
        for out_event in result.output_events:
            self._router.publish(out_event)

        # effect plan
        from src.app.core.state.extended_state import is_searching_for_user
        plan = self._effect_planner.plan(
            result,
            executing_kind=self._store.active_executing_kind,
            is_searching=is_searching_for_user(self._store),
        )

        # apply display
        if plan.display:
            self._display.apply_scene(result.mood, result.ui)

        # apply sounds
        for sound_cmd in plan.sounds:
            if sound_cmd.sound_name:
                self._sfx.play(sound_cmd.sound_name)
            if sound_cmd.tts_text:
                self._tts.speak_async(sound_cmd.tts_text)

        # execute domain
        if plan.execution:
            self._executor.execute(
                plan.execution.kind,
                {**plan.execution.payload, **event.payload},
                self._on_task_event,
            )

    def _on_task_event(self, event: Event) -> None:
        """도메인 실행 결과 이벤트 처리 (콜백)."""
        self._process_event(event)

    def _on_internal_event(self, event: Event) -> None:
        """내부 라우터 이벤트 로깅."""
        logger.debug("Internal event: %s", event.topic)

    def _signal_handler(self, signum, frame) -> None:
        logger.info("Signal %s received, shutting down...", signum)
        self._running = False

    def shutdown(self) -> None:
        """클린업."""
        self._running = False
        self._audio_worker.stop()
        self._vision_worker.stop()
        self._display.shutdown()
        self._sfx.shutdown()
        self._tts.shutdown()
        logger.info("RIO shutdown complete")


def main() -> None:
    """진입점."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    headless = "--headless" in sys.argv
    base_path = "."

    # base_path 인자 처리
    for arg in sys.argv[1:]:
        if not arg.startswith("--"):
            base_path = arg
            break

    app = RioApp(headless=headless, base_path=base_path)
    app.initialize()
    app.start()


if __name__ == "__main__":
    main()
