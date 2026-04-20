from __future__ import annotations

import importlib.util
import socket
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml

from src.app.core.config import resolve_repo_path

if TYPE_CHECKING:
    from src.app.main import RioOrchestrator


_VOICE_DEPS = {
    "sounddevice": "sounddevice",
    "faster_whisper": "faster-whisper",
}


@dataclass(slots=True)
class StartupReport:
    mic: str
    camera: str
    touch: str
    speaker: str
    voice: str
    home: str

    def format(self) -> str:
        lines = [
            "[RIO] startup report",
            f"  mic       : {self.mic}",
            f"  camera    : {self.camera}",
            f"  touch     : {self.touch}",
            f"  speaker   : {self.speaker}",
            f"  voice     : {self.voice}",
            f"  home      : {self.home}",
        ]
        return "\n".join(lines)


def _voice_status(orchestrator: "RioOrchestrator") -> str:
    if orchestrator.voice_backend is not None:
        cfg_path = resolve_repo_path("configs/voice.yaml")
        model = "unknown"
        language = "unknown"
        if cfg_path.exists():
            with cfg_path.open("r", encoding="utf-8") as handle:
                cfg = yaml.safe_load(handle) or {}
            asr = cfg.get("asr") or {}
            model = str(asr.get("model", "base"))
            language = str(asr.get("language", "ko"))
        return f"ENABLED (faster-whisper {model}, {language})"

    cfg_path = resolve_repo_path("configs/voice.yaml")
    if not cfg_path.exists():
        return "DISABLED (configs/voice.yaml missing)"

    missing = [pkg for mod, pkg in _VOICE_DEPS.items() if importlib.util.find_spec(mod) is None]
    if missing:
        return f"DISABLED (missing: {', '.join(missing)})"

    return "DISABLED (start failed or turned off)"


def _load_yaml_safe(relative_path: str) -> dict:
    path = resolve_repo_path(relative_path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def _mic_status(available: bool) -> str:
    if not available:
        return "MISSING"
    robot = _load_yaml_safe("configs/robot.yaml")
    voice = _load_yaml_safe("configs/voice.yaml")
    input_device = ((robot.get("audio") or {}).get("input_device")) if isinstance(robot, dict) else None
    voice_audio = (voice.get("audio") or {}) if isinstance(voice, dict) else {}
    backend = voice_audio.get("device")
    gain_pct = voice_audio.get("mic_gain_percent")
    gain_src = voice_audio.get("gain_target_source")
    parts = []
    if input_device:
        parts.append(str(input_device))
    if backend:
        parts.append(f"via {backend}")
    if gain_pct is not None and gain_src:
        parts.append(f"gain={gain_pct}%@{gain_src}")
    elif gain_pct is not None:
        parts.append(f"gain={gain_pct}%")
    if parts:
        return "OK (" + ", ".join(parts) + ")"
    return "OK"


def _speaker_status(available: bool) -> str:
    if not available:
        return "MISSING"
    robot = _load_yaml_safe("configs/robot.yaml")
    output_device = ((robot.get("audio") or {}).get("output_device")) if isinstance(robot, dict) else None
    if output_device:
        return f"OK ({output_device})"
    return "OK"


def _camera_status(available: bool) -> str:
    if not available:
        return "MISSING (/dev/video0)"
    robot = _load_yaml_safe("configs/robot.yaml")
    webcam = (robot.get("webcam") or {}) if isinstance(robot, dict) else {}
    idx = webcam.get("device_index", 0)
    w = webcam.get("width", 640)
    h = webcam.get("height", 480)
    fps = webcam.get("fps", 15)
    return f"OK (/dev/video{idx}, {w}x{h}@{fps}fps)"


def _touch_status(available: bool) -> str:
    if available:
        return "OK"
    return "MISSING (/proc/bus/input/devices)"


def _probe_home_bridge(control_url: str, timeout_s: float = 0.5) -> str:
    try:
        request = Request(url=control_url, method="GET")
        with urlopen(request, timeout=timeout_s) as resp:
            status = getattr(resp, "status", 200)
            return f"bridge: ok ({status})"
    except HTTPError as exc:
        # 어떤 HTTP 응답이든 돌아왔으면 브리지 프로세스는 살아있음.
        # ex) thinq_server.py 는 /device/control 에 GET 을 허용하지 않아 404 를 돌려주지만
        # 그래도 브리지는 기동 중.
        return f"bridge: ok ({exc.code})"
    except (TimeoutError, socket.timeout):
        return "bridge: timeout"
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return "bridge: timeout"
        return "bridge: unreachable"
    except Exception as exc:
        return f"bridge: error ({type(exc).__name__})"


def _home_status(orchestrator: "RioOrchestrator") -> str:
    devices_path = resolve_repo_path("configs/devices.yaml")
    base_url = "http://127.0.0.1"
    control_path = "/device/control"
    control_url: str | None = None
    if devices_path.exists():
        with devices_path.open("r", encoding="utf-8") as handle:
            cfg = yaml.safe_load(handle) or {}
        home = (cfg.get("home_client") or {}) if isinstance(cfg, dict) else {}
        base_url = str(home.get("base_url", base_url))
        control_path = str(home.get("control_path", control_path))
        control_url = home.get("control_url")
    resolved = control_url or f"{base_url.rstrip('/')}/{control_path.strip('/')}"
    probe = _probe_home_bridge(resolved)
    return f"{resolved}  [{probe}]"


def build_startup_report(orchestrator: "RioOrchestrator", *, no_voice: bool = False) -> StartupReport:
    snapshot = orchestrator.store.snapshot()
    caps = snapshot.extended.capabilities

    voice = "DISABLED (--no-voice)" if no_voice else _voice_status(orchestrator)
    return StartupReport(
        mic=_mic_status(caps.mic_available),
        camera=_camera_status(caps.camera_available),
        touch=_touch_status(caps.touch_available),
        speaker=_speaker_status(caps.speaker_available),
        voice=voice,
        home=_home_status(orchestrator),
    )


def print_startup_report(orchestrator: "RioOrchestrator", *, no_voice: bool = False) -> StartupReport:
    report = build_startup_report(orchestrator, no_voice=no_voice)
    print(report.format(), flush=True)
    return report


__all__ = ["StartupReport", "build_startup_report", "print_startup_report"]
