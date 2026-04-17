from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

import yaml

from src.app.adapters.audio.capture import AudioCapture
from src.app.adapters.audio.intent_normalizer import IntentNormalizer
from src.app.adapters.audio.stt import SpeechToTextAdapter
from src.app.adapters.audio.vad import VoiceActivityDetector
from src.app.adapters.camera.capture import WebcamCapture
from src.app.adapters.camera.storage import PhotoStorage
from src.app.adapters.display.renderer import Renderer
from src.app.adapters.home_client.client import HomeClient
from src.app.adapters.speaker.sfx import SFXPlayer
from src.app.adapters.speaker.tts import TTSPlayer
from src.app.adapters.touch.input import TouchInputAdapter
from src.app.adapters.vision.camera_stream import CameraStream
from src.app.adapters.vision.face_detector import FaceDetector
from src.app.adapters.vision.face_tracker import FaceTracker
from src.app.adapters.vision.gesture_detector import GestureDetector
from src.app.adapters.weather.client import WeatherClient
from src.app.core.bus.queue_bus import QueueBus
from src.app.core.bus.router import EventRouter
from src.app.core.config import resolve_repo_path
from src.app.core.events import topics
from src.app.core.events.models import Event
from src.app.core.safety.capabilities import detect_capabilities
from src.app.core.safety.heartbeat_monitor import HeartbeatMonitor
from src.app.core.scheduler.timer_scheduler import TimerScheduler
from src.app.core.state.extended_state import set_capabilities, set_deferred_intent
from src.app.core.state.models import ActionKind, ActivityState, RuntimeState
from src.app.core.state.reducers import ReducerPipeline
from src.app.core.state.store import RuntimeStore
from src.app.domains.behavior.effect_planner import EffectPlan, plan_effects
from src.app.domains.behavior.executor_registry import ExecutionRequest, ExecutionResult, ExecutorRegistry
from src.app.domains.behavior.interrupts import InterruptAction, evaluate_interrupt
from src.app.domains.games.service import GamesService
from src.app.domains.gesture.mapper import map_gesture_event
from src.app.domains.smart_home.service import SmartHomeService
from src.app.domains.timers.service import TimerService
from src.app.workers.audio_worker import AudioWorker
from src.app.workers.touch_worker import TouchWorker
from src.app.workers.vision_worker import VisionWorker


def _load_yaml(path: str) -> dict[str, object]:
    file_path = resolve_repo_path(path)
    if not file_path.exists():
        return {}
    with file_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _weather_execution_handler(client: WeatherClient) -> Callable[[ExecutionRequest], ExecutionResult]:
    def handler(request: ExecutionRequest) -> ExecutionResult:
        task_started = Event.create(
            topics.TASK_STARTED,
            "weather.handler",
            payload={"task_id": request.payload.get("task_id", request.trace_id or "weather"), "kind": ActionKind.WEATHER.value},
            trace_id=request.trace_id,
        )
        result = client.fetch_current(location=str(request.payload.get("location") or "seoul"))
        weather_event = Event.create(
            topics.WEATHER_RESULT,
            "weather.handler",
            payload=result,
            trace_id=request.trace_id,
        )
        terminal_topic = topics.TASK_SUCCEEDED if result.get("ok", True) else topics.TASK_FAILED
        terminal = Event.create(
            terminal_topic,
            "weather.handler",
            payload={
                "task_id": request.payload.get("task_id", request.trace_id or "weather"),
                "kind": ActionKind.WEATHER.value,
                "message": result.get("message", "weather complete"),
            },
            trace_id=request.trace_id,
        )
        return ExecutionResult(events=[task_started, weather_event, terminal])

    return handler


DANCE_DURATION_SECONDS = 10.0
PHOTO_COUNTDOWN_SECONDS = 3.0


def _photo_execution_handler_factory(
    orchestrator: "RioOrchestrator",
) -> Callable[[ExecutionRequest], ExecutionResult]:
    countdown_list = list(range(int(PHOTO_COUNTDOWN_SECONDS), 0, -1))

    def handler(request: ExecutionRequest) -> ExecutionResult:
        existing = orchestrator._photo_timer
        if existing is not None and existing.is_alive():
            return ExecutionResult(events=[])

        task_id = str(request.payload.get("task_id") or request.trace_id or uuid4().hex)
        trace_id = request.trace_id
        now = datetime.now(timezone.utc)
        orchestrator.photo_countdown_end_at = now + timedelta(seconds=PHOTO_COUNTDOWN_SECONDS)

        started = Event.create(
            topics.TASK_STARTED,
            "photo.handler",
            payload={
                "task_id": task_id,
                "kind": ActionKind.PHOTO.value,
                "countdown": list(countdown_list),
            },
            trace_id=trace_id,
            timestamp=now,
        )

        def finish() -> None:
            photo_path: str | None = None
            error_message: str | None = None
            try:
                if orchestrator.webcam_capture is not None:
                    photo_path = orchestrator.webcam_capture.capture(trace_id=trace_id)
            except Exception as exc:
                error_message = str(exc)

            orchestrator.photo_countdown_end_at = None
            if error_message is not None or photo_path is None:
                failed = Event.create(
                    topics.TASK_FAILED,
                    "photo.handler",
                    payload={
                        "task_id": task_id,
                        "kind": ActionKind.PHOTO.value,
                        "message": error_message or "photo capture unavailable",
                    },
                    trace_id=trace_id,
                )
                orchestrator.bus.publish(failed)
                return

            succeeded = Event.create(
                topics.TASK_SUCCEEDED,
                "photo.handler",
                payload={
                    "task_id": task_id,
                    "kind": ActionKind.PHOTO.value,
                    "photo_path": photo_path,
                    "countdown": list(countdown_list),
                },
                trace_id=trace_id,
            )
            orchestrator.bus.publish(succeeded)

        timer = threading.Timer(PHOTO_COUNTDOWN_SECONDS, finish)
        timer.daemon = True
        timer.start()
        orchestrator._photo_timer = timer
        return ExecutionResult(events=[started])

    return handler


def _dance_execution_handler_factory(
    orchestrator: "RioOrchestrator",
) -> Callable[[ExecutionRequest], ExecutionResult]:
    def handler(request: ExecutionRequest) -> ExecutionResult:
        task_id = request.payload.get("task_id", request.trace_id or "dance")
        trace_id = request.trace_id
        started = Event.create(
            topics.TASK_STARTED,
            "dance.handler",
            payload={"task_id": task_id, "kind": ActionKind.DANCE.value},
            trace_id=trace_id,
        )
        orchestrator.sfx.play("dance")

        def finish() -> None:
            orchestrator.sfx.stop("dance")
            succeeded = Event.create(
                topics.TASK_SUCCEEDED,
                "dance.handler",
                payload={
                    "task_id": task_id,
                    "kind": ActionKind.DANCE.value,
                    "message": "Dance routine finished",
                },
                trace_id=trace_id,
            )
            orchestrator.bus.publish(succeeded)

        timer = threading.Timer(DANCE_DURATION_SECONDS, finish)
        timer.daemon = True
        timer.start()
        orchestrator._dance_timer = timer
        return ExecutionResult(events=[started])

    return handler


@dataclass(slots=True)
class RioOrchestrator:
    bus: QueueBus = field(default_factory=QueueBus)
    router: EventRouter = field(default_factory=EventRouter)
    scheduler: TimerScheduler = field(default_factory=TimerScheduler)
    store: RuntimeStore = field(default_factory=RuntimeStore)
    reducer: ReducerPipeline = field(init=False)
    heartbeat_monitor: HeartbeatMonitor = field(default_factory=HeartbeatMonitor)
    renderer: Renderer = field(default_factory=Renderer)
    sfx: SFXPlayer = field(default_factory=SFXPlayer)
    tts: TTSPlayer = field(default_factory=TTSPlayer)
    registry: ExecutorRegistry = field(default_factory=ExecutorRegistry)
    audio_worker: AudioWorker | None = None
    vision_worker: VisionWorker | None = None
    touch_worker: TouchWorker | None = None
    event_log: list[Event] = field(default_factory=list)
    held_alerts: list[Event] = field(default_factory=list)
    webcam_capture: "WebcamCapture | None" = None
    photo_countdown_end_at: "datetime | None" = None
    _dance_timer: "threading.Timer | None" = None
    _photo_timer: "threading.Timer | None" = None

    def __post_init__(self) -> None:
        self.reducer = ReducerPipeline(self.store)
        capabilities = detect_capabilities()
        self.store.mutate(lambda state: setattr(state, "extended", set_capabilities(state.extended, capabilities)))
        if self.audio_worker is None:
            self.audio_worker = AudioWorker(
                bus=self.bus,
                capture=AudioCapture(),
                vad=VoiceActivityDetector(),
                stt=SpeechToTextAdapter(),
                normalizer=IntentNormalizer(),
            )
        if self.vision_worker is None:
            thresholds = _load_yaml("configs/thresholds.yaml")
            sample_hz = float((thresholds.get("presence") or {}).get("face_moved_sample_hz", 10))
            self.vision_worker = VisionWorker(
                bus=self.bus,
                stream=CameraStream(),
                detector=FaceDetector(),
                tracker=FaceTracker(sample_hz=sample_hz),
                gesture_detector=GestureDetector(),
            )
        if self.touch_worker is None:
            robot_cfg = _load_yaml("configs/robot.yaml")
            touch_cfg = (robot_cfg.get("touchscreen") or {}) if isinstance(robot_cfg, dict) else {}
            if bool(touch_cfg.get("enabled", True)):
                self.touch_worker = TouchWorker(
                    bus=self.bus,
                    adapter=TouchInputAdapter(),
                )
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        robot_cfg = _load_yaml("configs/robot.yaml")
        devices_cfg = _load_yaml("configs/devices.yaml")
        thresholds_cfg = _load_yaml("configs/thresholds.yaml")
        home_client = HomeClient(
            base_url=str((devices_cfg.get("home_client") or {}).get("base_url", "http://127.0.0.1")),
            control_path=str((devices_cfg.get("home_client") or {}).get("control_path", "/device/control")),
            control_url=((devices_cfg.get("home_client") or {}).get("control_url")),
            http_timeout_ms=int((thresholds_cfg.get("task") or {}).get("http_timeout_ms", 3000)),
            retry_count=int((thresholds_cfg.get("task") or {}).get("http_retry_count", 1)),
        )
        weather_client = WeatherClient(
            base_url=str((devices_cfg.get("weather") or {}).get("base_url", "https://api.example.invalid/weather")),
            http_timeout_ms=int((thresholds_cfg.get("task") or {}).get("http_timeout_ms", 3000)),
            retry_count=int((thresholds_cfg.get("task") or {}).get("http_retry_count", 1)),
        )
        photo_storage = PhotoStorage(root_dir=Path(str((robot_cfg.get("photo") or {}).get("storage_dir", "data/photos"))))
        self.webcam_capture = WebcamCapture(photo_storage)
        self.registry.register(ActionKind.PHOTO, _photo_execution_handler_factory(self))
        self.registry.register(ActionKind.TIMER_SETUP, TimerService(self.scheduler))
        self.registry.register(ActionKind.SMARTHOME, SmartHomeService(home_client))
        self.registry.register(ActionKind.GAME, GamesService())
        self.registry.register(ActionKind.DANCE, _dance_execution_handler_factory(self))
        self.registry.register(ActionKind.WEATHER, _weather_execution_handler(weather_client))

    def publish(self, event: Event) -> None:
        self.bus.publish(event)

    def _apply_plan(self, plan: EffectPlan, event: Event) -> None:
        self.renderer.render(plan.scene, event=event, face_center=event.payload.get("center"))
        for name in plan.sfx_names:
            self.sfx.play(name)
        for text in plan.tts_messages:
            self.tts.speak(text)

    def _clear_deferred_intent(self) -> dict[str, object] | None:
        deferred = self.store.snapshot().extended.deferred_intent
        if deferred is None:
            return None
        self.store.mutate(lambda state: setattr(state, "extended", set_deferred_intent(state.extended, None)))
        return deferred

    def _maybe_replay_deferred(self) -> list[Event]:
        events: list[Event] = []
        deferred = self._clear_deferred_intent()
        if deferred:
            replay = Event.create(
                topics.VOICE_INTENT_DETECTED,
                "orchestrator.deferred",
                payload=deferred,
            )
            events.extend(self.process_event(replay))
        if self.held_alerts:
            held = list(self.held_alerts)
            self.held_alerts.clear()
            for event in held:
                events.extend(self.process_event(event))
        return events

    def process_event(self, event: Event) -> list[Event]:
        self.event_log.append(event)
        self.router.publish(event)
        if event.topic == topics.SYSTEM_WORKER_HEARTBEAT:
            self.heartbeat_monitor.record(event)

        decision = evaluate_interrupt(self.store.snapshot(), event)
        if decision.action == InterruptAction.DROP:
            return [event]
        if decision.action == InterruptAction.DEFER_INTENT:
            self.store.mutate(
                lambda state: setattr(
                    state,
                    "extended",
                    set_deferred_intent(state.extended, decision.deferred_payload),
                )
            )
            return [event]
        if decision.action == InterruptAction.HOLD_ALERT:
            self.held_alerts.extend(decision.held_events)
            return [event]

        reduction = self.reducer.process(event)
        plan = plan_effects(reduction, event)
        self._apply_plan(plan, event)
        produced = [event, *reduction.emitted_events]
        for emitted in reduction.emitted_events:
            self.event_log.append(emitted)
            self.router.publish(emitted)

        if event.topic == topics.VISION_GESTURE_DETECTED:
            for mapped in map_gesture_event(event):
                produced.extend(self.process_event(mapped))

        if plan.executor_request is not None:
            execution = self.registry.dispatch(plan.executor_request)
            for produced_event in execution.events:
                produced.extend(self.process_event(produced_event))

        if (
            reduction.previous.activity_state != reduction.current.activity_state
            and reduction.current.activity_state == ActivityState.IDLE
        ):
            produced.extend(self._maybe_replay_deferred())

        return produced

    def run_until_idle(self, *, max_cycles: int = 32, now: datetime | None = None) -> list[Event]:
        processed: list[Event] = []
        for _ in range(max_cycles):
            cycle_events = self.run_once(now=now)
            if not cycle_events:
                break
            processed.extend(cycle_events)
        return processed

    def pump_workers(self, *, now: datetime | None = None) -> list[Event]:
        generated: list[Event] = []
        when = now or datetime.now(timezone.utc)
        if self.audio_worker:
            generated.extend(self.audio_worker.run_once(now=when))
        if self.vision_worker:
            generated.extend(self.vision_worker.run_once(now=when))
        if self.touch_worker:
            generated.extend(self.touch_worker.run_once(now=when))
        for event in self.scheduler.poll_due(now=when):
            self.bus.publish(event)
            generated.append(event)
        for degraded in self.heartbeat_monitor.check(now=when):
            self.bus.publish(degraded)
            generated.append(degraded)
        return generated

    def drain_bus(self) -> list[Event]:
        batch = self.bus.drain()
        processed: list[Event] = []
        for event in batch.events:
            processed.extend(self.process_event(event))
        return processed

    def run_once(self, *, now: datetime | None = None) -> list[Event]:
        self.pump_workers(now=now)
        return self.drain_bus()
