"""Main orchestrator entry point.

Wires together every module built in T-001..T-057 into a running system:

1. Build the :class:`EventBus` (cross-process queue) and :class:`Router`
   (in-process pub/sub).
2. Construct the state store and the :class:`Reducer` pipeline.
3. Build adapters (display, speaker, home-client, weather).
4. Instantiate domain services and register them with the executor
   registry.
5. Wire the interrupt gate + intent-replay logic into the main loop.
6. Start the audio/vision worker processes, passing in the bus queue and
   a stop event.
7. Run the event loop: pump worker events → gate → reducer → render.

Execution is cooperative: SIGINT/SIGTERM set the stop event, the loop
exits, workers are joined, and adapters shut down.
"""
from __future__ import annotations

import argparse
import logging
import multiprocessing as mp
import signal
import time
from pathlib import Path
from typing import Optional

from .adapters.display import Renderer, default_loader, make_backend as make_display_backend
from .adapters.home_client import HomeClientAdapter, HomeClientConfig
from .adapters.speaker import NullSFX, SFXPlayer, NullTTS, PyTtsx3TTS
from .adapters.touch import EvdevTouchInput, NullTouchInput
from .adapters.touch.gesture_mapper import TouchGestureMapper
from .core.bus import EventBus, Router
from .core.events import topics
from .core.events.models import Event
from .core.safety import HeartbeatMonitor, probe_all, merge_into
from .core.scheduler import TimerScheduler
from .core.state import Context, ExecutingKind, StateStore
from .core.state.reducers import Reducer
from .domains.behavior import (
    Decision,
    EffectPlanner,
    ExecutorRegistry,
    InterruptGate,
    pop_deferred,
    store_deferred,
)
from .domains.games import GamesService
from .domains.photo import PhotoService
from .domains.smart_home import SmartHomeService
from .domains.speech import aliases_from_triggers_yaml
from .domains.timers import TimerService
from .workers import audio_worker, vision_worker

_log = logging.getLogger(__name__)


def _default_aliases() -> dict:
    """MVP alias table used until ``configs/triggers.yaml`` is populated."""
    return {
        "camera.capture": ["사진 찍어줘", "사진 찍어", "찍어줘", "photo"],
        "timer.create": ["타이머", "알림", "알려줘"],
        "weather.current": ["날씨 알려줘", "오늘 날씨", "날씨"],
        "smarthome.aircon.on": ["에어컨 켜줘", "에어컨 켜", "냉방 켜줘"],
        "smarthome.aircon.off": ["에어컨 꺼줘", "에어컨 꺼", "냉방 꺼줘"],
        "smarthome.light.on": ["불 켜줘", "불 켜"],
        "smarthome.light.off": ["불 꺼줘", "불 꺼"],
        "smarthome.robot_cleaner.start": ["청소기 시작", "청소기 돌려"],
        "smarthome.tv.on": ["TV 켜줘", "티비 켜"],
        "smarthome.music.play": ["음악 틀어줘", "음악 재생"],
        "dance.start": ["춤춰", "댄스", "RIO dance"],
        "ui.game_mode.enter": ["게임 모드", "게임 시작"],
        "system.cancel": ["취소", "그만", "됐어"],
        "system.ack": ["응", "알았어", "오케이", "네"],
    }


class Orchestrator:
    def __init__(
        self,
        aliases: Optional[dict] = None,
        home_client_config: Optional[HomeClientConfig] = None,
        tick_interval_s: float = 0.02,
        debug_camera: bool = False,
    ) -> None:
        self._stop = mp.Event()
        self._bus = EventBus(capacity=1024)
        self._router = Router()
        self._store = StateStore()
        self._reducer = Reducer(self._store, self._router)
        self._scheduler = TimerScheduler(publish=self._bus.publish)
        self._gate = InterruptGate()
        self._executors = ExecutorRegistry()
        self._tick_s = tick_interval_s
        self._debug_camera = debug_camera

        self._aliases = aliases or _default_aliases()

        # Probe hardware and seed the capabilities map.
        probed = probe_all()
        merge_into(self._store.get().extended.capabilities, probed)

        # Display / speaker adapters.
        loader = default_loader()
        display_backend = make_display_backend(width_px=800, height_px=480)
        self._renderer = Renderer(loader=loader, backend=display_backend)
        self._sfx = SFXPlayer(loader=loader, backend=NullSFX())
        self._tts = PyTtsx3TTS() if probed.mic else NullTTS()

        # Domain services.
        self._photo = PhotoService(
            publish=self._bus.publish,
            sfx=self._sfx,
            composition=self._renderer.composition,
            camera=None,  # real snapshot adapter wired in production builds
        )
        self._timers = TimerService(publish=self._bus.publish, scheduler=self._scheduler)
        self._smart = SmartHomeService(
            publish=self._bus.publish,
            client=HomeClientAdapter(home_client_config or HomeClientConfig()),
        )
        self._games = GamesService(publish=self._bus.publish)

        self._executors.register(ExecutingKind.PHOTO, self._photo)
        self._executors.register(ExecutingKind.TIMER_SETUP, self._timers)
        self._executors.register(ExecutingKind.SMARTHOME, self._smart)
        self._executors.register(ExecutingKind.GAME, self._games)

        # Effect planner for SFX / TTS reactions.
        self._effects = EffectPlanner(sfx=self._sfx, tts=self._tts)

        # Touch input — publish events into the bus so they flow through the
        # same reducer pipeline as worker events.
        self._touch_mapper = TouchGestureMapper(publish=self._bus.publish)
        if probed.touch:
            # Auto-detect device path and axis ranges from evdev capabilities.
            self._touch_input = EvdevTouchInput()
        else:
            self._touch_input = NullTouchInput()

        # Heartbeat monitor.
        self._heartbeat = HeartbeatMonitor(
            publish=self._bus.publish, timeout_ms=5_000,
        )

        # Router subscriptions.
        self._router.subscribe_all(self._renderer.on_event)
        self._router.subscribe_all(self._effects.on_event)
        self._router.subscribe(topics.ACTIVITY_STATE_CHANGED, self._executors.on_activity_changed)
        self._router.subscribe(topics.SYSTEM_WORKER_HEARTBEAT, self._heartbeat.on_heartbeat)
        self._router.subscribe(topics.TIMER_EXPIRED, self._timers.on_timer_expired)
        self._router.subscribe(topics.ACTIVITY_STATE_CHANGED, self._on_activity_for_deferred)

        # Worker processes — wired up in start().
        self._audio_proc: Optional[mp.Process] = None
        self._vision_proc: Optional[mp.Process] = None

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        self._stop.clear()
        queue = self._bus.mp_queue()
        self._audio_proc = mp.Process(
            target=audio_worker.run,
            args=(queue, self._stop, self._aliases),
            name="rio-audio",
            daemon=True,
        )
        self._vision_proc = mp.Process(
            target=vision_worker.run,
            args=(queue, self._stop),
            kwargs={"debug_preview": self._debug_camera},
            name="rio-vision",
            daemon=True,
        )
        self._audio_proc.start()
        self._vision_proc.start()
        self._touch_input.start(self._touch_mapper.on_sample)
        _log.info("orchestrator started")

    def run_until_stopped(self) -> None:
        try:
            while not self._stop.is_set():
                self._tick(timeout_s=self._tick_s)
        finally:
            self.shutdown()

    def request_stop(self, *_args) -> None:
        self._stop.set()

    def shutdown(self) -> None:
        self._stop.set()
        self._touch_input.stop()
        self._scheduler.shutdown()
        for proc in (self._audio_proc, self._vision_proc):
            if proc is not None:
                proc.join(timeout=2.0)
        self._renderer.shutdown()
        self._bus.close()
        _log.info("orchestrator shut down")

    # -- per-tick work -----------------------------------------------------
    def _tick(self, timeout_s: float) -> None:
        event = self._bus.poll(timeout=timeout_s)
        now = time.monotonic()
        self._heartbeat.tick(now=now)
        if event is None:
            # Run a time-driven FSM pass by synthesising a minimal event
            # so thresholds (long_idle, away_timeout, listening timeout)
            # can fire without external input.
            event = Event(topic=topics.SYSTEM_WORKER_HEARTBEAT,
                          payload={"worker": "main", "status": "tick"},
                          timestamp=now, source="main")

        # Interrupt gate.
        activity = self._store.get().activity
        decision = self._gate.decide(activity, event)
        if decision is Decision.DROP:
            return
        if decision is Decision.DEFER:
            store_deferred(self._store.get().extended, event)
            return

        self._reducer.reduce(event)
        # After the FSM has settled, broadcast the raw input event so
        # subscribers that only care about the input (renderer face
        # tracking, heartbeat monitor, timer service cleanup) also see it.
        self._router.dispatch(event)
        self._renderer.render_frame()

    def _on_activity_for_deferred(self, event: Event) -> None:
        # On leaving Executing to Idle, replay the deferred intent if any.
        from_label = str(event.payload.get("from", ""))
        to_label = str(event.payload.get("to", ""))
        if from_label.startswith("executing(") and to_label == "idle":
            deferred = pop_deferred(self._store.get().extended)
            if deferred is not None:
                self._bus.publish(deferred)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="RIO orchestrator")
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument(
        "--debug-camera",
        action="store_true",
        help="Open a debug window in the vision worker showing the camera "
             "feed with face-detection overlays (q in that window hides it).",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))

    orch = Orchestrator(debug_camera=args.debug_camera)
    signal.signal(signal.SIGINT, orch.request_stop)
    signal.signal(signal.SIGTERM, orch.request_stop)
    orch.start()
    orch.run_until_stopped()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
