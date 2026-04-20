from __future__ import annotations

import base64
import json
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np

from src.app.core.config import resolve_repo_path

from .vad_rms import UtteranceMeta


def _ts() -> str:
    t = time.time()
    return time.strftime("%H:%M:%S", time.localtime(t)) + f".{int((t - int(t)) * 1000):03d}"


@dataclass
class RustFrontendConfig:
    worker_path: str
    config_path: Path
    startup_timeout_ms: int = 3000


@dataclass
class RustFrontendEvent:
    kind: str
    payload: dict[str, Any]
    audio: np.ndarray | None = None
    meta: UtteranceMeta | None = None


class RustAudioFrontend:
    def __init__(self, cfg: RustFrontendConfig):
        self.cfg = cfg
        self.events: "queue.Queue[RustFrontendEvent]" = queue.Queue(maxsize=32)
        self._process: subprocess.Popen[str] | None = None
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._stdin_lock = threading.Lock()
        self._stdout_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._stop.clear()
        self._ready.clear()
        worker_path = self._resolve_worker_path()
        cmd = [str(worker_path), "--config", str(self.cfg.config_path)]
        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._stdout_thread = threading.Thread(target=self._stdout_loop, name="sandbox-rust-stdout", daemon=True)
        self._stderr_thread = threading.Thread(target=self._stderr_loop, name="sandbox-rust-stderr", daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

        timeout_s = max(0.5, self.cfg.startup_timeout_ms / 1000.0)
        if not self._ready.wait(timeout=timeout_s):
            self.stop()
            raise RuntimeError("Rust audio worker did not become ready in time")

    def stop(self) -> None:
        self._stop.set()
        self._send({"type": "shutdown"})
        process = self._process
        if process is not None:
            try:
                process.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1.0)
        for thread in (self._stdout_thread, self._stderr_thread):
            if thread is not None:
                thread.join(timeout=1.0)
        self._process = None
        self._stdout_thread = None
        self._stderr_thread = None

    def send_asr_busy(self) -> None:
        self._send({"type": "asr_busy"})

    def send_asr_idle(self) -> None:
        self._send({"type": "asr_idle"})

    def _resolve_worker_path(self) -> Path:
        candidate = resolve_repo_path(self.cfg.worker_path)
        if candidate.exists():
            return candidate
        return Path(self.cfg.worker_path)

    def _stdout_loop(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = str(message.get("type") or "")
            if kind == "ready":
                self._ready.set()
                continue
            event = self._decode_event(kind, message)
            if event is None:
                continue
            try:
                self.events.put_nowait(event)
            except queue.Full:
                try:
                    self.events.get_nowait()
                except queue.Empty:
                    pass
                self.events.put_nowait(event)

    def _stderr_loop(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        for raw_line in process.stderr:
            line = raw_line.strip()
            if line:
                print(f"[{_ts()}] [rust] {line}")

    def _decode_event(self, kind: str, payload: dict[str, Any]) -> RustFrontendEvent | None:
        if kind == "utterance":
            encoded = str(payload.get("pcm_f32_b64") or "")
            if not encoded:
                return None
            audio = np.frombuffer(base64.b64decode(encoded), dtype=np.float32).copy()
            meta = UtteranceMeta(
                start_sample=int(payload.get("start_sample", 0)),
                end_sample=int(payload.get("end_sample", 0)),
                duration_ms=int(payload.get("duration_ms", 0)),
                passed_min_speech=True,
                peak=float(payload.get("peak", 0.0)),
                rms=float(payload.get("rms", 0.0)),
            )
            return RustFrontendEvent(kind=kind, payload=payload, audio=audio, meta=meta)
        if kind in {"speech_started", "speech_ended", "busy_drop", "trace", "error"}:
            return RustFrontendEvent(kind=kind, payload=payload)
        return None

    def _send(self, payload: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            return
        line = json.dumps(payload, ensure_ascii=False)
        with self._stdin_lock:
            try:
                process.stdin.write(line + "\n")
                process.stdin.flush()
            except BrokenPipeError:
                return
