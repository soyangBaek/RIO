from __future__ import annotations

import importlib.util
import logging
import os
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

import yaml

from src.app.adapters.audio.capture import AudioCapture
from src.app.adapters.audio.intent_normalizer import IntentNormalizer
from src.app.adapters.audio.live_voice_backend import (
    ASRParams,
    AudioParams,
    BackendConfig,
    BackendLaunchConfig,
    LiveVoiceBackend,
    RustAudioBackend,
    VADParams,
    VoiceBackend,
)
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
from src.app.core.state.models import ActionKind, ActivityState, ContextState, RuntimeState
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


_LOGGER = logging.getLogger(__name__)


def _load_yaml(path: str) -> dict[str, object]:
    file_path = resolve_repo_path(path)
    if not file_path.exists():
        return {}
    with file_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _missing_voice_dependencies(*, backend_type: str, fallback_to_python: bool) -> list[str]:
    required = {"faster_whisper": "faster-whisper"}
    if backend_type == "python" or fallback_to_python:
        required["sounddevice"] = "sounddevice"
    missing: list[str] = []
    for module_name, package_name in required.items():
        if importlib.util.find_spec(module_name) is None:
            missing.append(package_name)
    return missing


def _build_voice_backend(capture: AudioCapture) -> VoiceBackend | None:
    """Build the configured live mic backend.

    The existing audio/vad/asr/concurrency keys in configs/voice.yaml keep their
    meaning. Only the backend launch policy is new.
    """
    cfg = _load_yaml("configs/voice.yaml")
    if not cfg:
        return None

    audio = (cfg.get("audio") or {}) if isinstance(cfg, dict) else {}
    vad = (cfg.get("vad") or {}) if isinstance(cfg, dict) else {}
    asr = (cfg.get("asr") or {}) if isinstance(cfg, dict) else {}
    concurrency = (cfg.get("concurrency") or {}) if isinstance(cfg, dict) else {}
    backend = (cfg.get("backend") or {}) if isinstance(cfg, dict) else {}
    voice_logging = (cfg.get("logging") or {}) if isinstance(cfg, dict) else {}

    # run_rio_app.py --log info 가 설정하는 튜닝 모드 플래그.
    # 없으면 voice.yaml 값을 그대로 쓴다 (기존 동작 유지).
    voice_debug_tuning = os.environ.get("RIO_VOICE_DEBUG") == "1"

    log_level_name = str(voice_logging.get("level", "INFO")).strip().upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    if voice_debug_tuning:
        log_level = logging.DEBUG
    voice_logger = logging.getLogger("src.app.adapters.audio.live_voice_backend")
    voice_logger.setLevel(log_level)
    if log_level < logging.INFO and not any(
        getattr(h, "_rio_voice_debug", False) for h in voice_logger.handlers
    ):
        handler = logging.StreamHandler()
        handler.setLevel(log_level)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))
        handler._rio_voice_debug = True  # type: ignore[attr-defined]
        voice_logger.addHandler(handler)
        voice_logger.propagate = False

    backend_type = str(backend.get("type", "python")).strip().lower() or "python"
    if voice_debug_tuning and backend_type != "python":
        _LOGGER.info(
            "RIO_VOICE_DEBUG=1: forcing python voice backend (was %r) so per-frame RMS logs are emitted",
            backend_type,
        )
        backend_type = "python"
    fallback_to_python = bool(backend.get("fallback_to_python", True))
    missing = _missing_voice_dependencies(
        backend_type=backend_type,
        fallback_to_python=fallback_to_python,
    )
    missing_set = set(missing)

    threshold_value = float(vad.get("threshold", 350))
    if 0.0 <= threshold_value <= 1.0:
        _LOGGER.warning(
            "voice.yaml vad.threshold=%s looks like legacy Silero config; using RMS default 350 instead",
            threshold_value,
        )
        threshold_value = 350

    backend_cfg = BackendConfig(
        audio=AudioParams(
            device=audio.get("device"),
            sample_rate=int(audio.get("sample_rate", 16000)),
            channels=int(audio.get("channels", 1)),
            blocksize=int(audio.get("blocksize", 512)),
            dtype=str(audio.get("dtype", "float32")),
            mic_gain_percent=audio.get("mic_gain_percent"),
            gain_target_source=audio.get("gain_target_source"),
        ),
        vad=VADParams(
            threshold=int(round(threshold_value)),
            min_silence_duration_ms=int(vad.get("min_silence_duration_ms", 300)),
            speech_pad_ms=int(vad.get("speech_pad_ms", 30)),
            min_speech_ms=int(vad.get("min_speech_ms", 150)),
            sample_rate=int(audio.get("sample_rate", 16000)),
        ),
        asr=ASRParams(
            model=str(asr.get("model", "base")),
            language=str(asr.get("language", "ko")),
            beam_size=int(asr.get("beam_size", 1)),
            compute_type=str(asr.get("compute_type", "int8")),
            device=str(asr.get("device", "cpu")),
            no_speech_threshold=float(asr.get("no_speech_threshold", 0.6)),
            condition_on_previous_text=bool(asr.get("condition_on_previous_text", True)),
            min_logprob=float(asr.get("min_logprob", -1.0)),
            initial_prompt=asr.get("initial_prompt") or None,
        ),
        drop_while_busy=bool(concurrency.get("drop_while_busy", True)),
        launch=BackendLaunchConfig(
            type=backend_type,
            worker_path=str(
                backend.get(
                    "worker_path",
                    "native/bin/rio-audio-worker",
                )
            ),
            fallback_to_python=fallback_to_python,
            startup_timeout_ms=int(backend.get("startup_timeout_ms", 3000)),
        ),
    )

    def _build_python_backend() -> VoiceBackend | None:
        if "sounddevice" in missing_set:
            _LOGGER.warning(
                "Python live voice backend disabled; missing dependency: sounddevice",
            )
            return None
        return LiveVoiceBackend(capture=capture, config=backend_cfg)

    if "faster_whisper" in missing_set:
        _LOGGER.warning(
            "Live voice backend disabled; missing dependency: faster-whisper",
        )
        return None

    if backend_type == "rust":
        worker_path = resolve_repo_path(backend_cfg.launch.worker_path)
        if worker_path.exists():
            return RustAudioBackend(capture=capture, config=backend_cfg)
        _LOGGER.warning(
            "Rust audio worker not found at %s",
            worker_path,
        )
        if backend_cfg.launch.fallback_to_python:
            fallback = _build_python_backend()
            if fallback is not None:
                _LOGGER.warning("Falling back to Python live voice backend")
            return fallback
        return None

    return _build_python_backend()


DANCE_DURATION_SECONDS = 10.0
PHOTO_COUNTDOWN_SECONDS = 3.0
ALERT_AUTO_DISMISS_SECONDS = 15.0
WEATHER_DISPLAY_DURATION_SECONDS = 6.0


def _weather_execution_handler_factory(
    orchestrator: "RioOrchestrator",
    client: WeatherClient,
    display_seconds: float = WEATHER_DISPLAY_DURATION_SECONDS,
) -> Callable[[ExecutionRequest], ExecutionResult]:
    def handler(request: ExecutionRequest) -> ExecutionResult:
        task_id = request.payload.get("task_id", request.trace_id or "weather")
        task_started = Event.create(
            topics.TASK_STARTED,
            "weather.handler",
            payload={"task_id": task_id, "kind": ActionKind.WEATHER.value},
            trace_id=request.trace_id,
        )
        location_raw = request.payload.get("location")
        location = str(location_raw) if isinstance(location_raw, str) and location_raw else None
        result = client.fetch_current(location=location)
        if result.get("ok"):
            orchestrator.weather_display_end_at = datetime.now(timezone.utc) + timedelta(
                seconds=display_seconds
            )
            orchestrator.weather_icon_key = str(result.get("icon_key", "unknown"))
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
                "task_id": task_id,
                "kind": ActionKind.WEATHER.value,
                "message": result.get("message", "weather complete"),
            },
            trace_id=request.trace_id,
        )
        return ExecutionResult(events=[task_started, weather_event, terminal])

    return handler


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
    voice_backend: VoiceBackend | None = None
    event_log: list[Event] = field(default_factory=list)
    held_alerts: list[Event] = field(default_factory=list)
    webcam_capture: "WebcamCapture | None" = None
    photo_countdown_end_at: "datetime | None" = None
    weather_display_end_at: "datetime | None" = None
    weather_icon_key: "str | None" = None
    _dance_timer: "threading.Timer | None" = None
    _photo_timer: "threading.Timer | None" = None
    _alert_timeout_timer: "threading.Timer | None" = None
    _async_executor: ThreadPoolExecutor = field(
        default_factory=lambda: ThreadPoolExecutor(max_workers=2, thread_name_prefix="rio-exec"),
        init=False,
        repr=False,
    )
    _pending_futures: set[Future[ExecutionResult]] = field(default_factory=set, init=False, repr=False)
    _futures_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        self.reducer = ReducerPipeline(self.store)
        capabilities = detect_capabilities()
        self.store.mutate(lambda state: setattr(state, "extended", set_capabilities(state.extended, capabilities)))
        if self.audio_worker is None:
            # capture 를 공유해서 LiveVoiceBackend 가 이 큐에 cooked frame 을 주입하고
            # AudioWorker 가 tick 마다 꺼내 기존 VAD/STT/Normalizer 로 이벤트 발행.
            shared_capture = AudioCapture()
            self.audio_worker = AudioWorker(
                bus=self.bus,
                capture=shared_capture,
                vad=VoiceActivityDetector(),
                stt=SpeechToTextAdapter(),
                normalizer=IntentNormalizer(),
            )
            if self.voice_backend is None:
                self.voice_backend = _build_voice_backend(shared_capture)
        if self.vision_worker is None:
            thresholds = _load_yaml("configs/thresholds.yaml")
            robot_cfg = _load_yaml("configs/robot.yaml")
            presence = thresholds.get("presence") or {}
            vision = thresholds.get("vision") or {}
            webcam = (robot_cfg.get("webcam") or {}) if isinstance(robot_cfg, dict) else {}
            sample_hz = float(presence.get("face_moved_sample_hz", 10))
            # use_camera 는 실제 /dev/video0 존재 여부에 맞춘다. 없으면 mock dict 를
            # 돌려주는 stub 경로로 남겨 test/sandbox 환경에서도 안전하다.
            self.vision_worker = VisionWorker(
                bus=self.bus,
                stream=CameraStream(
                    device_index=int(webcam.get("device_index", 0)),
                    width=int(webcam.get("width", 640)),
                    height=int(webcam.get("height", 480)),
                    fps=int(webcam.get("fps", 15)),
                    use_camera=bool(capabilities.camera_available),
                ),
                detector=FaceDetector(
                    confidence_min=float(vision.get("face_confidence_min", 0.6)),
                ),
                tracker=FaceTracker(sample_hz=sample_hz),
                gesture_detector=GestureDetector(
                    confidence_min=float(vision.get("gesture_confidence_min", 0.75)),
                ),
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
        hc = home_client.health_check()
        if hc.get("ok"):
            _LOGGER.info("ThinQ bridge UP — %s", home_client.base_url)
        else:
            _LOGGER.warning("ThinQ bridge DOWN — %s (%s)", home_client.base_url, hc.get("message", ""))
        weather_cfg = devices_cfg.get("weather") or {}
        weather_client = WeatherClient(
            base_url=str(weather_cfg.get("base_url", "https://api.open-meteo.com/v1/forecast")),
            locations=dict(weather_cfg.get("locations") or {}),
            default_location=str(weather_cfg.get("default_location", "seoul")),
            http_timeout_ms=int((thresholds_cfg.get("task") or {}).get("http_timeout_ms", 3000)),
            retry_count=int((thresholds_cfg.get("task") or {}).get("http_retry_count", 1)),
        )
        weather_display_seconds = float(weather_cfg.get("display_seconds", WEATHER_DISPLAY_DURATION_SECONDS))
        photo_storage = PhotoStorage(root_dir=Path(str((robot_cfg.get("photo") or {}).get("storage_dir", "data/photos"))))
        self.webcam_capture = WebcamCapture(photo_storage)
        self.registry.register(ActionKind.PHOTO, _photo_execution_handler_factory(self))
        self.registry.register(ActionKind.TIMER_SETUP, TimerService(self.scheduler))
        self.registry.register(ActionKind.SMARTHOME, SmartHomeService(home_client))
        self.registry.register(ActionKind.GAME, GamesService())
        self.registry.register(ActionKind.DANCE, _dance_execution_handler_factory(self))
        self.registry.register(
            ActionKind.WEATHER,
            _weather_execution_handler_factory(self, weather_client, weather_display_seconds),
        )

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

        current_state = self.store.snapshot()
        decision = evaluate_interrupt(current_state, event)
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

        reduction = self.reducer.process(event, previous=current_state)
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
            if plan.executor_request.kind in {ActionKind.SMARTHOME, ActionKind.WEATHER}:
                self._dispatch_async(plan.executor_request)
            else:
                execution = self.registry.dispatch(plan.executor_request)
                for produced_event in execution.events:
                    produced.extend(self.process_event(produced_event))

        if reduction.previous.activity_state != reduction.current.activity_state:
            self._handle_alert_timeout(
                reduction.previous.activity_state,
                reduction.current.activity_state,
                event.trace_id,
            )
            self._handle_long_action_cancel(reduction, event)

        if reduction.previous.context_state != reduction.current.context_state:
            if reduction.current.context_state == ContextState.SLEEPY:
                self.sfx.play("sleepy", loops=-1)
            elif reduction.previous.context_state == ContextState.SLEEPY:
                self.sfx.stop("sleepy")

        if (
            reduction.previous.activity_state != reduction.current.activity_state
            and reduction.current.activity_state == ActivityState.IDLE
        ):
            produced.extend(self._maybe_replay_deferred())

        return produced

    def _dispatch_async(self, request: ExecutionRequest) -> None:
        future = self._async_executor.submit(self.registry.dispatch, request)
        with self._futures_lock:
            self._pending_futures.add(future)
        future.add_done_callback(self._handle_async_result)

    def _handle_async_result(self, future: Future[ExecutionResult]) -> None:
        with self._futures_lock:
            self._pending_futures.discard(future)
        try:
            execution = future.result()
        except Exception as exc:  # pragma: no cover - defensive
            self.bus.publish(
                Event.create(
                    topics.TASK_FAILED,
                    "orchestrator.async_executor",
                    payload={"kind": "async", "message": str(exc)},
                )
            )
            return
        for event in execution.events:
            self.bus.publish(event)

    def _handle_long_action_cancel(self, reduction, event: Event) -> None:
        if event.topic != topics.VOICE_INTENT_DETECTED:
            return
        intent = event.payload.get("intent")
        if intent not in {"system.cancel", "system.ack"}:
            return
        if reduction.current.activity_state != ActivityState.IDLE:
            return
        previous_kind = reduction.previous.extended.active_executing_kind
        if previous_kind == ActionKind.DANCE:
            self.sfx.stop("dance")
            pending = self._dance_timer
            if pending is not None and pending.is_alive():
                pending.cancel()
            self._dance_timer = None

    def _handle_alert_timeout(
        self,
        previous: ActivityState,
        current: ActivityState,
        trace_id: str | None,
    ) -> None:
        if current == ActivityState.ALERTING and previous != ActivityState.ALERTING:
            def _auto_dismiss() -> None:
                self.bus.publish(
                    Event.create(
                        topics.SYSTEM_ALERT_TIMEOUT,
                        "orchestrator.alert_timeout",
                        payload={"reason": "auto_dismiss"},
                        trace_id=trace_id,
                    )
                )

            existing = self._alert_timeout_timer
            if existing is not None and existing.is_alive():
                existing.cancel()
            timer = threading.Timer(ALERT_AUTO_DISMISS_SECONDS, _auto_dismiss)
            timer.daemon = True
            timer.start()
            self._alert_timeout_timer = timer
        elif previous == ActivityState.ALERTING and current != ActivityState.ALERTING:
            existing = self._alert_timeout_timer
            if existing is not None and existing.is_alive():
                existing.cancel()
            self._alert_timeout_timer = None

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

    def shutdown(self) -> None:
        if self.voice_backend is not None:
            try:
                self.voice_backend.stop()
            except Exception:
                pass
            self.voice_backend = None
        self._async_executor.shutdown(wait=False, cancel_futures=True)

    # ── context manager: voice backend 의 mic/VAD/Whisper 스레드 기동/정지 ───
    def __enter__(self) -> "RioOrchestrator":
        if self.voice_backend is not None:
            try:
                self.voice_backend.start()
            except Exception as exc:
                _LOGGER.warning("Voice backend start failed; continuing without mic voice: %s", exc)
                try:
                    self.voice_backend.stop()
                except Exception:
                    pass
                self.voice_backend = None
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.shutdown()
